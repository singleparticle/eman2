#!/home/hanxd/arc/EMAN2-bin/EMAN2/extlib/bin/python
#
#
#  08/13/2015
#  New version.
#  
from sparx import *
import os
import global_def
from   global_def import *
from   optparse  import OptionParser
import sys
from   numpy     import array
import types
from   logger    import Logger, BaseLogger_Files

def get_initial_ID(part_list, full_ID_dict):
	part_initial_id_list = []
	new_dict = {}
	for iptl in xrange(len(part_list)):
		id = full_ID_dict[part_list[iptl]]
		part_initial_id_list.append(id)
		new_dict[iptl] = id
	return part_initial_id_list, new_dict

def get_shrink_3dmask(nxinit,mask_file_name):
	from utilities import get_im,pad
	from fundamentals import resample
	mask3d = get_im(mask_file_name)
	nx2 = nxinit
	nx1 = mask3d.get_xsize()
	if nx1 == nx2:
		return mask3d
	else:
		shrinkage = float(nx2)/nx1
		#new_size  = nx1+5*2
        #pmask     =pad(mask3d,new_size, new_size, new_size,0.0)
		mask3d    =resample(mask3d,shrinkage)
        #cnt       = int((rpmask.get_xsize()-nx2)/2.)
        #mask3d    =Util.window(rpmask,nx2,nx2,nx2,cnt,cnt,cnt)
		return mask3d

def ali3d_mref_Kmeans_MPI(ref_list, outdir, this_data_list_file,Tracker): 
	from utilities      import model_circle, reduce_EMData_to_root, bcast_EMData_to_all, bcast_number_to_all, drop_image
	from utilities      import bcast_string_to_all, bcast_list_to_all, get_image, get_input_from_string, get_im
	from utilities      import get_arb_params, set_arb_params, drop_spider_doc, send_attr_dict
	from utilities      import get_params_proj, set_params_proj, model_blank, write_text_file
	from filter         import filt_params, filt_btwl, filt_ctf, filt_table, fit_tanh, filt_tanl
	from utilities      import rotate_3D_shift,estimate_3D_center_MPI
	from alignment      import Numrinit, prepare_refrings, proj_ali_incore
	from random         import randint
	from filter         import filt_ctf
	from utilities      import print_begin_msg, print_end_msg, print_msg
	from projection     import prep_vol, prgs, project, prgq, gen_rings_ctf
	from applications   import MPI_start_end
	import os
	import types
	from mpi            import mpi_bcast, mpi_comm_size, mpi_comm_rank, MPI_FLOAT, MPI_COMM_WORLD, mpi_barrier
	from mpi            import mpi_reduce, MPI_INT, MPI_SUM
	### - ----------------------------------------
	fourvar   = False
	debug     = False
	from logger import Logger,BaseLogger_Files
	log       = Logger()
	log   =Logger(BaseLogger_Files())
	log.prefix=outdir+"/"
	myid      = Tracker["constants"]["myid"]
	main_node = Tracker["constants"]["main_node"]
	number_of_proc     = Tracker["constants"]["nproc"]
	shrinkage = Tracker["shrinkage"]
	### input parameters
	maxit    = Tracker["constants"]["maxit"]
	ou       = Tracker["constants"]["radius"]
	ir       = Tracker["constants"]["ir"]
	rs       = Tracker["constants"]["rs"]
	xr       = Tracker["constants"]["xr"]
	yr       = Tracker["constants"]["yr"]
	ts       = Tracker["constants"]["ts"]
	delta    = Tracker["constants"]["delta"]
	an       = Tracker["constants"]["an"]
	center   = Tracker["constants"]["center"]
	nassign  = Tracker["constants"]["nassign"]
	nrefine  = Tracker["constants"]["nrefine"]
	CTF      = Tracker["constants"]["CTF"]
	snr      = Tracker["constants"]["snr"]
	ref_a    = Tracker["constants"]["ref_a"]
	sym      = Tracker["constants"]["sym"]
	npad     = Tracker["constants"]["npad"]
	termprec = Tracker["constants"]["stoprnct"]
	maskfile = Tracker["constants"] ["mask3D"]
	focus    = Tracker["constants"]["focus3Dmask"]
	user_func_name  = Tracker["constants"]["user_func"]
	frequency_low_pass   = Tracker["frequency_low_pass"]

	###--------------------------

	if os.path.exists(outdir): ERROR('Output directory exists, please change the name and restart the program', "Kmref_ali3d_MPI ", 1, myid)
	mpi_barrier(MPI_COMM_WORLD)

	###

	if myid == main_node:	
		os.mkdir(outdir)
		import global_def
		global_def.LOGFILE =  os.path.join(outdir, global_def.LOGFILE)
		log.add("Kmref_ali3d_MPI - Traditional Kmeans clustering  !")
	mpi_barrier(MPI_COMM_WORLD)

	######
	Tracker["applyctf"] = False
	data, old_shifts    = get_shrink_data_huang(Tracker,Tracker["nxinit"],this_data_list_file,Tracker["constants"]["partstack"],myid, main_node, number_of_proc, preshift = True)

	from time import time	

	if debug:
		from time import sleep
		while not os.path.exists(outdir):
			print  "Node ",myid,"  waiting..."
			sleep(5)

		finfo = open(os.path.join(outdir, "progress%04d"%myid), 'w')
		frec  = open( os.path.join(outdir, "recons%04d"%myid), "w" )
	else:
		finfo = None
		frec  = None

	xrng        = get_input_from_string(xr)
	if  yr == "-1":  yrng = xrng
	else          :  yrng = get_input_from_string(yr)
	step        = get_input_from_string(ts)
	delta       = get_input_from_string(delta)
	lstp = min( len(xrng), len(yrng), len(step), len(delta) )
	if an == "-1":
		an = []
		for i in xrange(len(xrng)):   an.append(-1)
	else:
		from  alignment	    import proj_ali_incore_local
		an      = get_input_from_string(an)
	first_ring  = int(ir)
	rstep       = int(rs)
	last_ring   = int(int(ou)*shrinkage+.5)
	center      = int(center)
	image_start, image_end = MPI_start_end(len(Tracker["this_data_list"]), number_of_proc, myid)
	numref = len(ref_list)
	nx      = ref_list[0].get_xsize()
	if last_ring < 0:       last_ring = nx//2 - 2
	fscmask = model_circle(last_ring, nx, nx, nx)
	stack = Tracker["constants"]["stack"]
	if myid == main_node:
		import user_functions
		user_func = user_functions.factory[user_func_name]
		log.add("Input stack                 : %s"%(stack))
		#log.add("Reference volumes           : %s"%(ref_vol))	
		log.add("Number of reference volumes : %i"%(numref))
		log.add("Output directory            : %s"%(outdir))
		log.add("User function               : %s"%(user_func_name))
		log.add("Maskfile                    : %s"%(maskfile))
		log.add("Inner radius                : %i"%(first_ring))
		log.add("Outer radius                : %i"%(last_ring))
		log.add("Ring step                   : %i"%(rstep))
		log.add("X search range              : %s"%(xrng))
		log.add("Y search range              : %s"%(yrng))
		log.add("Translational step          : %s"%(step))
		log.add("Angular step                : %s"%(delta))
		log.add("Angular search range        : %s"%(an))
		log.add("Number of assignments in each iteration   : %i"%(nassign))
		log.add("Number of alignments in each iteration    : %i"%(nrefine))
		log.add("Number of iterations                      : %i"%(lstp*maxit) )
		log.add("Center type                 : %i"%(center))
		log.add("CTF correction              : %s"%(CTF))
		log.add("Signal-to-Noise Ratio       : %f"%(snr))
		log.add("Reference projection method : %s"%(ref_a))
		log.add("Symmetry group              : %s"%(sym))
		log.add("Percentage of change for termination: %f"%(termprec))
		log.add("User function               : %s"%(user_func_name))
		log.add("total number of particles                 : %d"%len(Tracker["this_data_list"]))
		log.add("shrinkage is                              : %f"%shrinkage)
		log.add("the text file for get_shrink_data is %s"%this_data_list_file)
	if maskfile:
		if type(maskfile) is types.StringType:  mask3D = get_shrink_3dmask(Tracker["nxinit"],maskfile)
		else: 	                                mask3D = maskfile
	else:  mask3D = model_circle(last_ring, nx, nx, nx)

	numr     = Numrinit(first_ring, last_ring, rstep, "F")
	mask2D   = model_circle(last_ring, nx, nx) - model_circle(first_ring, nx, nx)
	total_nima = len(Tracker["this_data_list"])
	nima       = len(data)
	list_of_particles  =Tracker["this_data_list"]
	Tracker["total_stack"]  = total_nima
    #####
	if debug:
		finfo.write( "Image_start, image_end: %d %d\n" %(image_start, image_end) )
		finfo.flush()
	start_time = time()
	if myid == main_node:
		log.add( "Time to read data: %d\n" % (time()-start_time) );start_time = time()
	#  Initialize Particle ID and set group number to non-existant -1
	assignment = [-1]*len(data)
 	for im in xrange(len(data)):
		data[im].set_attr_dict({'ID':list_of_particles[im], 'group':-1})
	if fourvar:
		from reconstruction import rec3D_MPI
		from statistics     import varf3d_MPI
		#  Compute Fourier variance
		vol, fscc = rec3D_MPI(data, snr, sym, fscmask, os.path.join(outdir, "resolution0000"), myid, main_node, finfo=frec, npad=npad)
		varf = varf3d_MPI(data, os.path.join(outdir, "ssnr0000"), None, vol, last_ring, 1.0, 1, CTF, 1, sym, myid)
		if myid == main_node:   
			varf = 1.0/varf
			varf.write_image( os.path.join(outdir,"varf0000.hdf") )
	else:
		varf = None
	if myid == main_node:
		for  iref in xrange(numref):
			ref_list[iref].write_image(os.path.join(outdir, "volf0000.hdf"), iref)
	mpi_barrier( MPI_COMM_WORLD )

	if CTF:
		#if(data[0].get_attr("ctf_applied") > 0.0):  ERROR("mref_ali3d_MPI does not work for CTF-applied data", "mref_ali3d_MPI", 1, myid)
		from reconstruction import rec3D_MPI
	else:
		from reconstruction import rec3D_MPI_noCTF

	if debug:
		finfo.write( '%d loaded  \n' % len(data) )
		finfo.flush()

	#  this is needed for gathering of pixel errors
	disps = []
	recvcount = []
	for im in xrange(number_of_proc):
		if im == main_node:  disps.append(0)
		else:                  disps.append(disps[im-1] + recvcount[im-1])
		ib, ie = MPI_start_end(total_nima, number_of_proc, im)
		recvcount.append( ie - ib )

	total_iter = 0
	tr_dummy = Transform({"type":"spider"})

	Niter = int(lstp*maxit*(nassign + nrefine) )
	for Iter in xrange(Niter):
		N_step = (Iter%(lstp*(nassign+nrefine)))/(nassign+nrefine)
		if Iter%(nassign+nrefine) < nassign:
			runtype = "ASSIGNMENT"
		else:
			runtype = "REFINEMENT"

		total_iter += 1
		if myid == main_node:
			log.add("\n%s ITERATION #%3d,  inner iteration #%3d\nDelta = %4.1f, an = %5.2f, xrange = %5.2f, yrange = %5.2f, step = %5.2f" \
                        %(runtype, total_iter, Iter, delta[N_step], an[N_step], xrng[N_step],yrng[N_step],step[N_step]))
			start_ime = time()
	
		peaks = [ -1.0e23]*nima
		if runtype=="REFINEMENT":
			trans = [tr_dummy]*nima
			pixer = [0.0]*nima
			if(an[N_step] > 0):
				from utilities    import even_angles
				ref_angles = even_angles(delta[N_step], symmetry=sym, method = ref_a, phiEqpsi = "Zero")
				# generate list of angles
				from alignment import generate_list_of_reference_angles_for_search
				list_of_reference_angles = \
				generate_list_of_reference_angles_for_search(ref_angles, sym=sym)
				del ref_angles
			else:  list_of_reference_angles = [[1.0,1.0]]
 
		cs = [0.0]*3
		for iref in xrange(numref):
			if myid==main_node:
				volft = get_im(os.path.join(outdir, "volf%04d.hdf"%(total_iter-1)), iref)
			else:
				volft=model_blank(nx,nx,nx)
			bcast_EMData_to_all(volft, myid, main_node)
			volft, kb = prep_vol(volft)

			if CTF:
				previous_defocus = -1.0
				if runtype=="REFINEMENT":
					start_time = time()
					prjref = prgq( volft, kb, nx, delta[N_step], ref_a, sym, MPI=True)
					if myid == main_node:
						log.add( "Calculation of projections: %d" % (time()-start_time) );start_time = time()
					del volft, kb
			else:
				if runtype=="REFINEMENT":
					start_time = time()
					refrings = prepare_refrings( volft, kb, nx, delta[N_step], ref_a, sym, numr)
					if myid == main_node:
						log.add( "Initial time to prepare rings: %d" % (time()-start_time) );start_time = time()
					del volft, kb

			start_time = time()
			for im in xrange(nima):
				if CTF:
					ctf = data[im].get_attr( "ctf" )
					if runtype=="REFINEMENT":
						if ctf.defocus != previous_defocus:
							previous_defocus = ctf.defocus
							rstart_time = time()
							refrings = gen_rings_ctf( prjref, nx, ctf, numr)
							if myid == main_node:
								log.add( "Repeated time to prepare rings: %d" % (time()-rstart_time) );rstart_time = time()

				if runtype=="ASSIGNMENT":
					phi,tht,psi,s2x,s2y = get_params_proj(data[im])
					ref = prgs( volft, kb, [phi,tht,psi,-s2x,-s2y])
					if CTF:  ref = filt_ctf( ref, ctf )
					peak = ref.cmp("ccc",data[im],{"mask":mask2D, "negative":0})
					if not(finfo is None):
						finfo.write( "ID,iref,peak: %6d %d %8.5f\n" % (list_of_particles[im],iref,peak) )
				else:
					if an[N_step] == -1:
						peak, pixel_error = proj_ali_incore(data[im],refrings,numr,xrng[N_step],yrng[N_step],step[N_step])
					else:
						peak, pixel_error = proj_ali_incore_local(data[im], refrings, list_of_reference_angles, numr,\
																	xrng[N_step], yrng[N_step], step[N_step], an[N_step])
					if not(finfo is None):
						phi,tht,psi,s2x,s2y = get_params_proj(data[im])
						finfo.write( "ID,iref,peak,trans: %6d %d %f %f %f %f %f %f\n"%(list_of_particles[im],iref,peak,phi,tht,psi,s2x,s2y) )
						finfo.flush()

				if peak > peaks[im]:
					peaks[im] = peak
					data[im].set_attr('group', iref)
					if runtype=="REFINEMENT":
						pixer[im] = pixel_error
						trans[im] = data[im].get_attr( "xform.projection" )
					if not(finfo is None):
						finfo.write( " current best\n" )
						finfo.flush()
				else:
					if not(finfo is None):
						finfo.write( "\n" )
						finfo.flush()
			if myid == main_node:
				log.add( "Time to process particles for reference %3d: %d" % (iref, time()-start_time) );start_time = time()


		del peaks
		if runtype=="ASSIGNMENT":  del volft, kb, ref
		else:
			if CTF: del prjref
			del refrings
			if an[N_step] > 0: del list_of_reference_angles


		#  compute number of particles that changed assignment and how many are in which group
		nchng = 0
		npergroup = [0]*numref
		for im in xrange(nima):
			iref = data[im].get_attr('group')
			npergroup[iref] += 1
			if iref != assignment[im]:
				assignment[im] = iref
				nchng += 1
		nchng = mpi_reduce(nchng, 1, MPI_INT, MPI_SUM, 0, MPI_COMM_WORLD)
		npergroup = mpi_reduce(npergroup, numref, MPI_INT, MPI_SUM, 0, MPI_COMM_WORLD)
		npergroup = map(int, npergroup)
		terminate  = 0
		empty_group =0
		if myid == main_node:
			nchng = int(nchng[0])
			precn = 100*float(nchng)/float(total_nima)
			msg = " Number of particles that changed assignments %7d, percentage of total: %5.1f"%(nchng, precn)
			log.add(msg)
			msg = " Group       number of particles"
			log.add(msg)
			for iref in xrange(numref):
				msg = " %5d       %7d"%(iref+1, npergroup[iref])
				log.add(msg)
				if npergroup[iref]==0:
					empty_group =1
			if precn <= termprec:  
				terminate = 1
			if empty_group ==1:
				terminate = 1
		terminate = mpi_bcast(terminate, 1, MPI_INT, 0, MPI_COMM_WORLD)
		terminate = int(terminate[0])
		empty_group = mpi_bcast(empty_group, 1, MPI_INT, 0, MPI_COMM_WORLD)
		empty_group = int(empty_group[0])
		if empty_group ==1: break # program stops whenever empty_group appears!
		if runtype=="REFINEMENT":
			for im in xrange(nima):
				data[im].set_attr('xform.projection', trans[im])

			if center == -1:
				cs[0], cs[1], cs[2], dummy, dummy = estimate_3D_center_MPI(data, total_nima, myid, number_of_proc, main_node)				
				if myid == main_node:
					msg = " Average center x = %10.3f        Center y = %10.3f        Center z = %10.3f"%(cs[0], cs[1], cs[2])
					log.add(msg)
				cs = mpi_bcast(cs, 3, MPI_FLOAT, main_node, MPI_COMM_WORLD)
				cs = [-float(cs[0]), -float(cs[1]), -float(cs[2])]
				rotate_3D_shift(data, cs)
			#output pixel errors
			from mpi import mpi_gatherv
			recvbuf = mpi_gatherv(pixer, nima, MPI_FLOAT, recvcount, disps, MPI_FLOAT, main_node, MPI_COMM_WORLD)
			mpi_barrier(MPI_COMM_WORLD)
			if myid == main_node:
				recvbuf = map(float, recvbuf)
				from statistics import hist_list
				lhist = 20
				region, histo = hist_list(recvbuf, lhist)
				if region[0] < 0.0:  region[0] = 0.0
				msg = "      Histogram of pixel errors\n      ERROR       number of particles"
				log.add(msg)
				for lhx in xrange(lhist):
					msg = " %10.3f      %7d"%(region[lhx], histo[lhx])
					log.add(msg)
				del region, histo
			del recvbuf

		#if CTF: del vol
		fscc = [None]*numref

		if fourvar and runtype=="REFINEMENT":
			sumvol = model_blank(nx, nx, nx)

		sart_time = time()
		for iref in xrange(numref):
			#  3D stuff
			from time import localtime, strftime
			if CTF: volref, fscc[iref] = rec3D_MPI(data, snr, sym, fscmask, os.path.join(outdir, "resolution_%02d_%04d"%(iref, total_iter)), myid, main_node, index = iref, npad = npad, finfo=frec)
			else:    volref, fscc[iref] = rec3D_MPI_noCTF(data, sym, fscmask, os.path.join(outdir, "resolution_%02d_%04d"%(iref, total_iter)), myid, main_node, index = iref, npad = npad, finfo=frec)
			if myid == main_node:
				log.add( "Time to compute 3D: %d" % (time()-start_time) );start_time = time()

			if myid == main_node:
				volref.write_image(os.path.join(outdir, "vol%04d.hdf"%( total_iter)), iref)
				if fourvar and runtype=="REFINEMENT":
					sumvol += volref
			del volref

		if runtype=="REFINEMENT":
			if fourvar:
				varf = varf3d_MPI(data, os.path.join(outdir, "ssnr%04d"%total_iter), None,sumvol,last_ring, 1.0, 1, CTF, 1, sym, myid)
				if myid == main_node:   
					varf = 1.0/varf
					varf.write_image( os.path.join(outdir,"varf%04d.hdf"%total_iter) )

		if myid == main_node:
			refdata = [None]*7
			refdata[0] = numref
			refdata[1] = outdir
			refdata[2] = None
			refdata[3] = total_iter
			refdata[4] = varf
			refdata[5] = mask3D
			refdata[6] = (runtype=="REFINEMENT") # whether align on 50S, this only happens at refinement step
			user_func( refdata )

		#  here we  write header info
		mpi_barrier(MPI_COMM_WORLD)
		#start_time = time()
		if runtype=="REFINEMENT":
			par_str = ['xform.projection', 'ID', 'group']
		else:
			par_str = ['group', 'ID' ]
	        #if myid == main_node:
		#	from utilities import file_type
	        #	if file_type(stack) == "bdb":
	        #		from utilities import recv_attr_dict_bdb
	        #		recv_attr_dict_bdb(main_node, stack, data, par_str, image_start, image_end, number_of_proc)
	        #	else:
	        # 		from utilities import recv_attr_dict
	        #		recv_attr_dict(main_node, stack, data, par_str, image_start, image_end, number_of_proc)
	        #else:		send_attr_dict(main_node, data, par_str, image_start, image_end)
		if terminate == 1:
			if myid == main_node:
				log.add("Kmref_ali3d_MPI terminated due to small number of objects changing assignments")
			final_list = get_sorting_params(Tracker,data)
			res_groups = get_groups_from_partition(final_list, Tracker["this_data_list"], numref)
			if myid ==main_node:
				final_list_saved_file =os.path.join(outdir,"list2.txt")
				write_text_file(final_list,final_list_saved_file)
				for igrp in xrange(len(res_groups)):
						saved_file = os.path.join(outdir,"Class%d.txt"%igrp)
						write_text_file(res_groups[igrp],saved_file)
			mpi_barrier(MPI_COMM_WORLD)
			Tracker["this_partition"]=final_list
			break
		if myid == main_node:
			log.add( "Time to write headers: %d\n" % (time()-start_time) )
		mpi_barrier(MPI_COMM_WORLD)
	######writing paritition only in the end of the program
	mpi_barrier(MPI_COMM_WORLD)
	if nrefine!=0:
		par_str = ['xform.projection', 'ID', 'group']
	else:
		par_str = ['group', 'ID' ]
	"""	
	if myid == main_node:
		from utilities import file_type
		if file_type(stack) == "bdb":
			from utilities import recv_attr_dict_bdb
			recv_attr_dict_bdb(main_node, stack, data, par_str, image_start, image_end, number_of_proc)
		else:
			from utilities import recv_attr_dict
			recv_attr_dict(main_node, stack, data, par_str, image_start, image_end, number_of_proc)
	else:		send_attr_dict(main_node, data, par_str, image_start, image_end)
	"""
	if myid == main_node:
		log.add("Kmref_ali3d_MPI is done!")
	return empty_group

def mref_ali3d_EQ_Kmeans(ref_list, outdir, particle_list_file,Tracker):
	from utilities      import model_circle, reduce_EMData_to_root, bcast_EMData_to_all, bcast_number_to_all, drop_image
	from utilities      import bcast_string_to_all, bcast_list_to_all, get_image, get_input_from_string, get_im
	from utilities      import get_arb_params, set_arb_params, drop_spider_doc, send_attr_dict
	from utilities      import get_params_proj, set_params_proj, model_blank, wrap_mpi_bcast, write_text_file
	from filter         import filt_params, filt_btwl, filt_ctf, filt_table, fit_tanh, filt_tanl
	from utilities      import rotate_3D_shift,estimate_3D_center_MPI
	from alignment      import Numrinit, prepare_refrings, proj_ali_incore
	from random         import randint, random
	from filter         import filt_ctf
	from utilities      import print_begin_msg, print_end_msg, print_msg, read_text_file
	from projection     import prep_vol, prgs, project, prgq, gen_rings_ctf
	from morphology     import binarize
	import os
	import types
	from mpi            import mpi_bcast, mpi_comm_size, mpi_comm_rank, MPI_FLOAT, MPI_COMM_WORLD, mpi_barrier
	from mpi            import mpi_reduce, mpi_gatherv, mpi_scatterv, MPI_INT, MPI_SUM
	from applications import MPI_start_end
	mpi_comm = MPI_COMM_WORLD
	#####
	fourvar   = False
	from logger import Logger,BaseLogger_Files
	log       = Logger()
	log   =Logger(BaseLogger_Files())
	log.prefix=outdir+"/"
	myid      = Tracker["constants"]["myid"]
	main_node = Tracker["constants"]["main_node"]
	number_of_proc     = Tracker["constants"]["nproc"]
	shrinkage = Tracker["shrinkage"]
	### input parameters
	maxit    = Tracker["constants"]["maxit"]
	ou       = Tracker["constants"]["radius"]
	ir       = Tracker["constants"]["ir"]
	rs       = Tracker["constants"]["rs"]
	xr       = Tracker["constants"]["xr"]
	yr       = Tracker["constants"]["yr"]
	ts       = Tracker["constants"]["ts"]
	delta    = Tracker["constants"]["delta"]
	an       = Tracker["constants"]["an"]
	center   = Tracker["constants"]["center"]
	nassign  = Tracker["constants"]["nassign"]
	nrefine  = Tracker["constants"]["nrefine"]
	CTF      = Tracker["constants"]["CTF"]
	snr      = Tracker["constants"]["snr"]
	ref_a    = Tracker["constants"]["ref_a"]
	sym      = Tracker["constants"]["sym"]
	npad     = Tracker["constants"]["npad"]
	termprec = Tracker["constants"]["stoprnct"]
	maskfile = Tracker["constants"] ["mask3D"]
	focus    = Tracker["constants"]["focus3Dmask"]
	partstack = Tracker["constants"]["partstack"]
	debug    = False
	user_func_name  = Tracker["constants"]["user_func"]
	frequency_low_pass   = Tracker["frequency_low_pass"]
	######
	Tracker["applyctf"] = False
	data, old_shifts =  get_shrink_data_huang(Tracker,Tracker["nxinit"],particle_list_file,partstack,myid,main_node,number_of_proc,preshift=True)
	if myid == main_node:
		if os.path.exists(outdir):  nx = 1
		else:  nx = 0
	else:  nx = 0
	ny = bcast_number_to_all(nx, source_node = main_node)
	
	if ny == 1:  ERROR('Output directory exists, please change the name and restart the program', "mref_ali3d_iter", 1,myid)
	mpi_barrier(MPI_COMM_WORLD)

	if myid == main_node:	
		os.mkdir(outdir)
		import global_def
		global_def.LOGFILE =  os.path.join(outdir, global_def.LOGFILE)
		log.add("Equal K-means  ")
	mpi_barrier(MPI_COMM_WORLD)

	from time import time	

	if debug:
		from time import sleep
		while not os.path.exists(outdir):
			print  "Node ",myid,"  waiting..."
			sleep(5)

		finfo = open(os.path.join(outdir, "progress%04d"%myid), 'w')
		frec  = open( os.path.join(outdir, "recons%04d"%myid), "w" )
	else:
		finfo = None
		frec  = None

	xrng        = get_input_from_string(xr)
	if  yr == "-1":  yrng = xrng
	else          :  yrng = get_input_from_string(yr)
	step        = get_input_from_string(ts)
	delta       = get_input_from_string(delta)
	lstp = min( len(xrng), len(yrng), len(step), len(delta) )
	if (an == "-1"):
		an = []
		for i in xrange(len(xrng)):   an.append(-1)
	else:
		from  alignment	    import proj_ali_incore_local
		an      = get_input_from_string(an)

	first_ring  = int(ir)
	rstep       = int(rs)
	last_ring   = int(int(ou)*shrinkage+.5)
	center      = int(center)
	image_start, image_end = MPI_start_end(len(Tracker["this_data_list"]), number_of_proc, myid)
	numref = len(ref_list)
	nx      = ref_list[0].get_xsize()
	if last_ring < 0:	last_ring = nx//2 - 2
	if (myid == main_node):
		import user_functions
		user_func = user_functions.factory[user_func_name]
		log.add("mref_ali3d_MPI")
		log.add("Input stack                               : %s"%(Tracker["constants"]["stack"]))
		#log.add("Reference volumes                         : %s"%(ref_vol))	
		log.add("Number of reference volumes               : %i"%(numref))
		log.add("Output directory                          : %s"%(outdir))
		log.add("User function                             : %s"%(user_func_name))
		if(focus != None):  \
		log.add("Maskfile 3D for focused clustering        : %s"%(focus))
		log.add("Overall 3D mask applied in user function  : %s"%(maskfile))
		log.add("Inner radius                              : %i"%(first_ring))
		log.add("Outer radius                              : %i"%(last_ring))
		log.add("Ring step                                 : %i"%(rstep))
		log.add("X search range                            : %s"%(xrng))
		log.add("Y search range                            : %s"%(yrng))
		log.add("Translational step                        : %s"%(step))
		log.add("Angular step                              : %s"%(delta))
		log.add("Angular search range                      : %s"%(an))
		log.add("Number of assignments in each iteration   : %i"%(nassign))
		log.add("Number of alignments in each iteration    : %i"%(nrefine))
		log.add("Number of iterations                      : %i"%(lstp*maxit) )
		log.add("Center type                               : %i"%(center))
		log.add("CTF correction                            : %s"%(CTF))
		log.add("Signal-to-Noise Ratio                     : %f"%(snr))
		log.add("Reference projection method               : %s"%(ref_a))
		log.add("Symmetry group                            : %s"%(sym))
		log.add("Percentage of change for termination      : %f"%(termprec))
		log.add("User function                             : %s"%(user_func_name))
		log.add("total number of particles                 : %d"%len(Tracker["this_data_list"]))
		log.add("shrinkage is                              : %f"%shrinkage)
		log.add("the particle id files for get_shrink_dat is %s"%particle_list_file) 
	if(maskfile):
		if(type(maskfile) is types.StringType): mask3D = get_shrink_3dmask(Tracker["nxinit"],maskfile) 
		else: 	                                mask3D = maskfile
	else        :  mask3D = model_circle(last_ring, nx, nx, nx)

	numr     = Numrinit(first_ring, last_ring, rstep, "F")
	mask2D   = model_circle(last_ring, nx, nx)
	if(first_ring > 1):  mask2D -= model_circle(first_ring, nx, nx)

	total_nima = Tracker["total_stack"]
	nima       = len(data)
	list_of_particles  =Tracker["this_data_list"]

	'''
	if(myid == main_node):	
		total_nima = EMUtil.get_image_count(stack)
		list_of_particles = range(total_nima)
	
	else:
		total_nima =0

	total_nima = bcast_number_to_all(total_nima, source_node = main_node)

	if(myid != main_node):
		list_of_particles = [-1]*total_nima

	list_of_particles = bcast_list_to_all(list_of_particles, myid,  source_node = main_node)

	image_start, image_end = MPI_start_end(total_nima, number_of_proc, myid)
	# create a list of images for each node
	list_of_particles = list_of_particles[image_start: image_end]
	nima = len(list_of_particles)
	'''
	if debug:
		finfo.write( "Image_start, image_end: %d %d\n" %(image_start, image_end) )
		finfo.flush()

	start_time = time()
	#  Here the assumption is that input are always volumes.  It should be most likely be changed so optionally these are group assignments.
	#  Initialize Particle ID and set group number to non-existant -1
	for im in xrange(nima):
		data[im].set_attr_dict({'ID':list_of_particles[im], 'group':-1})
	if(myid == 0):
		log.add( "Time to read data: %d" % (time()-start_time) );start_time = time()

	if myid == main_node:
		refdata = [None]*7
		for  iref in xrange(numref):
			ref_list[iref].write_image(os.path.join(outdir, "vol0000.hdf"), iref)
		refdata[0] = numref
		refdata[1] = outdir
		refdata[2] = Tracker["frequency_low_pass"]
		refdata[3] = 0
		refdata[4] = ref_list
		refdata[5] = mask3D
		refdata[6] = False # whether to align on 50S, this only happens at refinement step
		user_func(refdata)
		#vol.write_image(os.path.join(outdir, "volf0000.hdf"), iref)
	mpi_barrier( MPI_COMM_WORLD )

	if CTF:
		if(data[0].get_attr_default("ctf_applied",0) > 0):  ERROR("mref_ali3d_MPI does not work for CTF-applied data", "mref_ali3d_MPI", 1, myid)
		from reconstruction import rec3D_MPI
	else:
		from reconstruction import rec3D_MPI_noCTF

	if debug:
		finfo.write( '%d loaded  \n' % len(data) )
		finfo.flush()

	#  this is needed for gathering of pixel errors
	disps = []
	recvcount = []
	for im in xrange(number_of_proc):
		if( im == main_node ):  disps.append(0)
		else:                   disps.append(disps[im-1] + recvcount[im-1])
		ib, ie = MPI_start_end(total_nima, number_of_proc, im)
		recvcount.append( ie - ib )

	total_iter = 0
	tr_dummy = Transform({"type":"spider"})

	if(focus != None):
		if(myid == main_node):
			vol = get_shrink_3dmask(Tracker["nxinit"],focus)
		else:
			vol =  model_blank(nx, nx, nx)
		bcast_EMData_to_all(vol, myid, main_node)
		focus, kb = prep_vol(vol)

	Niter = int(lstp*maxit*(nassign + nrefine) )
	for Iter in xrange(Niter):
		N_step = (Iter%(lstp*(nassign+nrefine)))/(nassign+nrefine)
		if Iter%(nassign+nrefine) < nassign:
			runtype = "ASSIGNMENT"
		else:
			runtype = "REFINEMENT"

		total_iter += 1
		if(myid == main_node):
			log.add("\n%s ITERATION #%3d,  inner iteration #%3d\nDelta = %4.1f, an = %5.2f, xrange = %5.2f, yrange = %5.2f, step = %5.2f  \
			"%(runtype, total_iter, Iter, delta[N_step], an[N_step], xrng[N_step],yrng[N_step],step[N_step]))
			start_ime = time()
	
		peaks =  [ [ -1.0e23 for im in xrange(nima) ] for iref in xrange(numref) ]
		if runtype=="REFINEMENT":
 			trans = [ [ tr_dummy for im in xrange(nima) ] for iref in xrange(numref) ]
			pixer = [ [  0.0     for im in xrange(nima) ] for iref in xrange(numref) ]
			if(an[N_step] > 0):
				from utilities    import even_angles
				ref_angles = even_angles(delta[N_step], symmetry=sym, method = ref_a, phiEqpsi = "Zero")
				# generate list of angles
				from alignment import generate_list_of_reference_angles_for_search
				list_of_reference_angles = \
				generate_list_of_reference_angles_for_search(ref_angles, sym=sym)
				del ref_angles
			else:  list_of_reference_angles = [[1.0,1.0]]

		cs = [0.0]*3
		for iref in xrange(numref):
			if(myid == main_node):
				volft = get_im(os.path.join(outdir, "volf%04d.hdf"%(total_iter-1)), iref)
			else:
				volft =  model_blank(nx, nx, nx)
			bcast_EMData_to_all(volft, myid, main_node)

			volft, kb = prep_vol(volft)
			if CTF:
				previous_defocus = -1.0
				if runtype=="REFINEMENT":
					start_time = time()
					prjref = prgq( volft, kb, nx, delta[N_step], ref_a, sym, MPI=True)
					if(myid == 0):
						log.add( "Calculation of projections: %d" % (time()-start_time) );start_time = time()
					del volft, kb

			else:
				if runtype=="REFINEMENT":
					start_time = time()
					refrings = prepare_refrings( volft, kb, nx, delta[N_step], ref_a, sym, numr)
					if(myid == 0):
						log.add( "Initial time to prepare rings: %d" % (time()-start_time) );start_time = time()
					del volft, kb


			start_time = time()
			for im in xrange(nima):
				if(CTF):
					ctf = data[im].get_attr( "ctf" )
					if runtype=="REFINEMENT":
						if(ctf.defocus != previous_defocus):
							previous_defocus = ctf.defocus
							rstart_time = time()
							refrings = gen_rings_ctf( prjref, nx, ctf, numr)
							if(myid == 0):
								log.add( "Repeated time to prepare rings: %d" % (time()-rstart_time) );rstart_time = time()

				if runtype=="ASSIGNMENT":
					phi,tht,psi,s2x,s2y = get_params_proj(data[im])
					ref = prgs( volft, kb, [phi,tht,psi,-s2x,-s2y])
					if CTF:  ref = filt_ctf( ref, ctf )
					if(focus != None):  mask2D = binarize( prgs( focus, kb, [phi,tht,psi,-s2x,-s2y]) )  #  Should be precalculated!!
					peak = ref.cmp("ccc",data[im],{"mask":mask2D, "negative":0})
					if not(finfo is None):
						finfo.write( "ID, iref, peak: %6d %d %8.5f\n" % (list_of_particles[im],iref,peak) )
				else:
					if(an[N_step] == -1):
						peak, pixel_error = proj_ali_incore(data[im], refrings, numr, xrng[N_step], yrng[N_step], step[N_step])
					else:
						peak, pixel_error = proj_ali_incore_local(data[im], refrings, list_of_reference_angles, numr, \
																	xrng[N_step], yrng[N_step], step[N_step], an[N_step],sym=sym)
					if not(finfo is None):
						phi,tht,psi,s2x,s2y = get_params_proj(data[im])
						finfo.write( "ID, iref, peak,t rans: %6d %d %f %f %f %f %f %f\n"%(list_of_particles[im],iref,peak,phi,tht,psi,s2x,s2y) )
						finfo.flush()

				peaks[iref][im] = peak
				if runtype=="REFINEMENT":
					pixer[iref][im] = pixel_error
					trans[iref][im] = data[im].get_attr( "xform.projection" )

			if(myid == 0):
				log.add( "Time to process particles for reference %3d: %d" % (iref, time()-start_time) );start_time = time()


		if runtype=="ASSIGNMENT":  del volft, kb, ref
		else:
			if CTF: del prjref
			del refrings
			if(an[N_step] > 0): del list_of_reference_angles


		#  send peak values to the main node, do the assignments, and bring them back
		from numpy import float32, empty, inner, abs
		if( myid == 0 ):
			dtot = empty( (numref, total_nima), dtype = float32)
		for  iref in xrange(numref):
			recvbuf = mpi_gatherv(peaks[iref], nima, MPI_FLOAT, recvcount, disps, MPI_FLOAT, main_node, MPI_COMM_WORLD)
			if( myid == 0 ): dtot[iref] = recvbuf
		del recvbuf


		#  The while loop over even angles delta should start here.
		#  prepare reference directions
		from utilities import even_angles, getvec
		refa = even_angles(60.0)
		numrefang = len(refa)
		refanorm = empty( (numrefang, 3), dtype = float32)
		for i in xrange(numrefang):
			tmp = getvec(refa[i][0], refa[i][1])
			for j in xrange(3):
				refanorm[i][j] = tmp[j]
		del  refa, tmp
		transv = empty( (nima, 3), dtype = float32)
		if runtype=="ASSIGNMENT":
			for im in xrange(nima):
				trns = data[im].get_attr( "xform.projection" )
				for j in xrange(3):
					transv[im][j] = trns.at(2,j)
		else:
			# For REFINEMENT we have a problem, as the exact angle is known only after the next step of assigning projections.
			# So, we will assume it is the one with max peak
			for im in xrange(nima):
				qt = -1.0e23
				it = -1
				for iref in xrange(numref):
					pt = peaks[iref][im]
					if(pt > qt):
						qt = pt
						it = iref
				for j in xrange(3):
					transv[im][j] = trans[it][im].at(2,j)
		#  We have all vectors, now create a list of assignments of images to references
		refassign = [-1]*nima
		for im in xrange(nima):
			refassign[im] = abs(inner(refanorm,transv[im])).argmax()
		assigntorefa = mpi_gatherv(refassign, nima, MPI_INT, recvcount, disps, MPI_INT, main_node, MPI_COMM_WORLD)
		assigntorefa = map(int, assigntorefa)
		del refassign, refanorm, transv


		"""
		#  Trying to use ISAC code for EQ-Kmeans  PAP 03/21/2015
		if myid == main_node:

			for imrefa in xrange(numrefang):
				from utilities import findall
				N = findall(imrefa, assigntorefa)
				current_nima = len(N)
				if( current_nima >= numref and report_error == 0):
					tasi = [[] for iref in xrange(numref)]
					maxasi = current_nima//numref
					nt = current_nima
					kt = numref
					K = range(numref)

					d = empty( (numref, current_nima), dtype = float32)
					for ima in xrange(current_nima):
						for iref in xrange(numref):  d[iref][ima] = dtot[iref][N[ima]]

			d = empty( (numref, total_nima), dtype = float32)
			for ima in xrange(total_nima):
				for iref in xrange(numref):  d[iref][ima] = dtot[iref][N[ima]]
			id_list_long = Util.assign_groups(str(d.__array_interface__['data'][0]), numref, nima) # string with memory address is passed as parameters
			del d
			id_list = [[] for i in xrange(numref)]
			maxasi = total_nima/numref
			for i in xrange(maxasi*numref):
				id_list[i/maxasi].append(id_list_long[i])
			for i in xrange(total_nima%maxasi):
				id_list[id_list_long[-1]].append(id_list_long[maxasi*numref+i])
			for iref in xrange(numref):
				id_list[iref].sort()

			assignment = [0]*total_nima
			for iref in xrange(numref):
				for im in id_list[iref]: assignment[im] = iref
		else:
			assignment = [0]*total_nima
		mpi_barrier(MPI_COMM_WORLD)
		#belongsto = mpi_bcast(belongsto, nima, MPI_INT, main_node, MPI_COMM_WORLD)
		#belongsto = map(int, belongsto)
		"""
		if myid == main_node:
			SA = False
			asi = [[] for iref in xrange(numref)]
			report_error = 0
			for imrefa in xrange(numrefang):
				from utilities import findall
				N = findall(imrefa, assigntorefa)
				current_nima = len(N)
				if( current_nima >= numref and report_error == 0):
					tasi = [[] for iref in xrange(numref)]
					maxasi = current_nima//numref
					nt = current_nima
					kt = numref
					K = range(numref)

					d = empty( (numref, current_nima), dtype = float32)
					for ima in xrange(current_nima):
						for iref in xrange(numref):  d[iref][ima] = dtot[iref][N[ima]]

					while nt > 0 and kt > 0:
						l = d.argmax()
						group = l//current_nima
						ima   = l-current_nima*group
						if SA:
							J = [0.0]*numref
							sJ = 0
							Jc = [0.0]*numref
							for iref in xrange(numref):
								J[iref] = exp(d[iref][ima]/T)
								sJ += J[iref]
							for iref in xrange(numref):
								J[iref] /= sJ
							Jc[0] = J[0]
							for iref in xrange(1, numref):
								Jc[iref] = Jc[iref-1]+J[iref]
							sss = random()
							for group in xrange(numref):
								if( sss <= Jc[group]): break
						tasi[group].append(N[ima])
						N[ima] = -1
						for iref in xrange(numref):  d[iref][ima] = -1.e10
						nt -= 1
						masi = len(tasi[group])
						if masi == maxasi:
							for im in xrange(current_nima):  d[group][im] = -1.e10
							kt -= 1
					else:
						for ima in xrange(current_nima):
							if N[ima] > -1:
								qm = -1.e10
								for iref in xrange(numref):
									qt = dtot[iref][N[ima]]
									if( qt > qm ):
										qm = qt
										group = iref
								tasi[group].append(N[ima])

					del d, N, K
					if  SA:  del J, Jc
					for iref in xrange(numref):
						asi[iref] += tasi[iref]
					del tasi
				else:
					report_error = 1
			#  This should be deleted only once we know that the number of images is sufficiently large, see below.
			del dtot

		else:
			assignment = []
			report_error = 0

		report_error = bcast_number_to_all(report_error, source_node = main_node)
		if report_error == 1:  ERROR('Number of images within a group too small', "mref_ali3d_MPI", 1, myid)
		if myid == main_node:
			assignment = [0]*total_nima
			for iref in xrange(numref):
				for im in xrange(len(asi[iref])):
					assignment[asi[iref][im]] = iref
			del asi
		
		"""
		if myid == main_node:
			assignment = [0]*total_nima
			for iref in xrange(numref):
				for im in xrange(len(asi[iref])):
					assignment[asi[iref][im]] = iref
			del asi
		"""

		'''
		if myid == main_node:
			SA = False
			maxasi = total_nima//numref
			asi = [[] for iref in xrange(numref)]
			nt = total_nima
			kt = numref
			K = range(numref)
			N = range(total_nima)

			while nt > 0 and kt > 1:
				l = d.argmax()
				group = l//total_nima
				ima   = l-total_nima*group
				if SA:
					J = [0.0]*numref
					sJ = 0
					Jc = [0.0]*numref
					for iref in xrange(numref):
						J[iref] = exp(d[iref][ima]/T)
						sJ += J[iref]
					for iref in xrange(numref):
						J[iref] /= sJ
					Jc[0] = J[0]
					for iref in xrange(1, numref):
						Jc[iref] = Jc[iref-1]+J[iref]
					sss = random()
					for group in xrange(numref):
						if( sss <= Jc[group]): break
				asi[group].append(N[ima])
				for iref in xrange(numref):  d[iref][ima] = -1.e10
				nt -= 1
				masi = len(asi[group])
				if masi == maxasi:
					for im in xrange(total_nima):  d[group][im] = -1.e10
					kt -= 1
			else:
				mas = [len(asi[iref]) for iref in xrange(numref)]
				group = mas.index(min(mas))
				del mas
				for im in xrange(total_nima):
					kt = 0
					go = True
					while(go and kt < numref):
						if d[kt][im] > -1.e10:
							asi[group].append(im)
							go = False
						kt += 1

			assignment = [0]*total_nima
			for iref in xrange(numref):
				for im in xrange(len(asi[iref])):
					assignment[asi[iref][im]] = iref

			del asi, d, N, K
			if  SA:  del J, Jc


		else:
			assignment = []
		'''

		assignment = mpi_scatterv(assignment, recvcount, disps, MPI_INT, recvcount[myid], MPI_INT, main_node, MPI_COMM_WORLD)
		assignment = map(int, assignment)


		#  compute number of particles that changed assignment and how many are in which group
		nchng = 0
		npergroup = [0]*numref
		for im in xrange(nima):
			iref = data[im].get_attr('group')
			npergroup[assignment[im]] += 1
			if( iref != assignment[im]): nchng += 1
			data[im].set_attr('group', assignment[im])
		nchng = mpi_reduce(nchng, 1, MPI_INT, MPI_SUM, 0, MPI_COMM_WORLD)
		npergroup = mpi_reduce(npergroup, numref, MPI_INT, MPI_SUM, 0, MPI_COMM_WORLD)
		npergroup = map(int, npergroup)
		terminate = 0
		if( myid == 0 ):
			nchng = int(nchng[0])
			precn = 100*float(nchng)/float(total_nima)
			msg = " Number of particles that changed assignments %7d, percentage of total: %5.1f"%(nchng, precn)
			log.add(msg)
			msg = " Group       number of particles"
			log.add(msg)
			for iref in xrange(numref):
				msg = " %5d       %7d"%(iref+1, npergroup[iref])
				log.add(msg)
			if(precn <= termprec):  terminate = 1
		terminate = mpi_bcast(terminate, 1, MPI_INT, 0, MPI_COMM_WORLD)
		terminate = int(terminate[0])

		if runtype=="REFINEMENT":
			for im in xrange(nima):
				data[im].set_attr('xform.projection', trans[assignment[im]][im])
				pixer[0][im] = pixer[assignment[im]][im]
			pixer = pixer[0]

			if(center == -1):
				cs[0], cs[1], cs[2], dummy, dummy = estimate_3D_center_MPI(data, total_nima, myid, number_of_proc, main_node)				
				if myid == main_node:
					msg = " Average center x = %10.3f        Center y = %10.3f        Center z = %10.3f"%(cs[0], cs[1], cs[2])
					log.add(msg)
				cs = mpi_bcast(cs, 3, MPI_FLOAT, main_node, MPI_COMM_WORLD)
				cs = [-float(cs[0]), -float(cs[1]), -float(cs[2])]
				rotate_3D_shift(data, cs)
			#output pixel errors
			recvbuf = mpi_gatherv(pixer, nima, MPI_FLOAT, recvcount, disps, MPI_FLOAT, main_node, MPI_COMM_WORLD)
			mpi_barrier(MPI_COMM_WORLD)
			if(myid == main_node):
				recvbuf = map(float, recvbuf)
				from statistics import hist_list
				lhist = 20
				region, histo = hist_list(recvbuf, lhist)
				if(region[0] < 0.0):  region[0] = 0.0
				msg = "      Histogram of pixel errors\n      ERROR       number of particles"
				log.add(msg)
				for lhx in xrange(lhist):
					msg = " %10.3f      %7d"%(region[lhx], histo[lhx])
					log.add(msg)
				del region, histo
			del recvbuf

		fscc = [None]*numref
		if fourvar and runtype=="REFINEMENT":
			sumvol = model_blank(nx, nx, nx)
		start_time = time()
		for iref in xrange(numref):
			#  3D stuff
			from time import localtime, strftime
			if(CTF): volref, fscc[iref] = rec3D_MPI(data, snr, sym, model_circle(last_ring, nx, nx, nx),\
			 os.path.join(outdir, "resolution_%02d_%04d"%(iref, total_iter)), myid, main_node, index = iref, npad = npad, finfo=frec)
			else:    volref, fscc[iref] = rec3D_MPI_noCTF(data, sym, model_circle(last_ring, nx, nx, nx),\
			 os.path.join(outdir, "resolution_%02d_%04d"%(iref, total_iter)), myid, main_node, index = iref, npad = npad, finfo=frec)
			if(myid == 0):
				log.add( "Time to compute 3D: %d" % (time()-start_time) );start_time = time()

			if(myid == main_node):
				volref.write_image(os.path.join(outdir, "vol%04d.hdf"%( total_iter)), iref)
				if fourvar and runtype=="REFINEMENT":
					sumvol += volref
			del volref
		"""
		if runtype=="REFINEMENT":
			if fourvar:
				varf = varf3d_MPI(data, os.path.join(outdir, "ssnr%04d"%total_iter), None,sumvol,last_ring, 1.0, 1, CTF, 1, sym, myid)
				if myid == main_node:   
					varf = 1.0/varf
					varf.write_image( os.path.join(outdir,"varf%04d.hdf"%total_iter) )
		"""
		if(myid == main_node):
			frcs={}
			for iref in xrange(numref):
				frc=read_text_file(os.path.join(outdir, "resolution_%02d_%04d"%(iref, total_iter)),-1)
				frcs[iref]=frc
			refdata = [None]*7
			refdata[0] = numref
			refdata[1] = outdir
			refdata[2] = frequency_low_pass
			refdata[3] = total_iter
			refdata[4] = None
			refdata[5] = mask3D
			refdata[6] = (runtype=="REFINEMENT") # whether to align on 50S, this only happens at refinement step
			user_func(refdata)

		mpi_barrier(MPI_COMM_WORLD)
		if terminate ==0: # headers are only updated when the program is going to terminate
			start_time = time()
			if nrefine!=0:
				par_str = ['xform.projection', 'ID', 'group']
			else:
				par_str = ['group', 'ID' ]
			"""
	        	if myid == main_node:
				from utilities import file_type
	        		if(file_type(stack) == "bdb"):
	        			from utilities import recv_attr_dict_bdb
	        			recv_attr_dict_bdb(main_node, stack, data, par_str, image_start, image_end, number_of_proc)
	        		else:
	        			from utilities import recv_attr_dict
	        			recv_attr_dict(main_node, stack, data, par_str, image_start, image_end, number_of_proc)
	        	else:		send_attr_dict(main_node, data, par_str, image_start, image_end)
			"""
			if(myid == 0):
				log.add( "Time to write headers: %d\n" % (time()-start_time) );start_time = time()
			mpi_barrier(MPI_COMM_WORLD)
			#if myid==main_node:
				#log.add("mref_ali3d_MPI" )
				#from utilities import cmdexecute
                        	#cmd = "{} {} {} {}".format("sxheader.py",stack,"--params=xform.projection", "--export="+os.path.join(outdir, "ali3d_params_%03d.txt"%total_iter))
                        	#cmdexecute(cmd)
			#mpi_barrier(MPI_COMM_WORLD)		
		if terminate==1:
			final_list = get_sorting_params(Tracker,data)
			if myid ==main_node:
				final_list_saved_file =os.path.join(outdir, "list2.txt")
				write_text_file(final_list,final_list_saved_file)
			mpi_barrier(MPI_COMM_WORLD)
			Tracker["this_partition"]=final_list
			break
	#if myid==main_node:
	#	log.add("mref_ali3d_MPI finishes")
	#	from utilities import cmdexecute
	#	cmd = "{} {} {} {}".format("sxheader.py",stack,"--params=xform.projection", "--export="+os.path.join(outdir,"ali3d_params.txt"))
	#	cmdexecute(cmd)
def print_upper_triangular_matrix(data_table_dict,N_indep,log_main):
		msg =""
		for i in xrange(N_indep):
			msg +="%7d"%i
		log_main.add(msg)
		for i in xrange(N_indep):
			msg ="%5d "%i
			for j in xrange(N_indep):
				if i<j:
					msg +="%5.2f "%data_table_dict[(i,j)]
				else:
					msg +="      "
			log_main.add(msg)
			
def print_a_line_with_timestamp(string_to_be_printed ):                 
	line = strftime("%Y-%m-%d_%H:%M:%S", localtime()) + " =>"
 	print(line,string_to_be_printed)
	return string_to_be_printed

def convertasi(asig,K):
	p=[]
	for k in xrange(K):
		l = []
		for i in xrange(len(asig)):
			if asig[i]==k: l.append(i)
		l=array(l,"int32")
		l.sort()
		p.append(l)
	return p
def prepare_ptp(data_list,K):
	num_of_pt=len(data_list)
	ptp=[]
	for ipt in xrange(num_of_pt):
		ptp.append([])
	for ipt in xrange(num_of_pt):
		nc =len(data_list[ipt])
		asig=[-1]*nc
		for i in xrange(nc):
			asig[i]=data_list[ipt][i]
		ptp[ipt] = convertasi(asig,K)
	return ptp

def print_dict(dict,theme):
		line = strftime("%Y-%m-%d_%H:%M:%S", localtime()) + " =>"
		print(line,theme)
		spaces = "                    "
		for key, value in sorted( dict.items() ):
			if(key != "constants"):  print("                    => ", key+spaces[len(key):],":  ",value)
"""
def checkstep(item, keepchecking, myid, main_node):
	from utilities import bcast_number_to_all
        if(myid == main_node):
                if keepchecking:
                        if(os.path.exists(item)):
                                doit = 0
                        else:
                                doit = 1
                                keepchecking = False
                else:
                        doit = 1
        else:
                doit = 1
        doit = bcast_number_to_all(doit, source_node = main_node)
        return doit, keepchecking
"""
def get_resolution_mrk01(vol, radi, nnxo, fscoutputdir, mask_option):
        # this function is single processor
        #  Get updated FSC curves, user can also provide a mask using radi variable
	import types
	from statistics import fsc
	from utilities import model_circle, get_im
	from filter import fit_tanh1
	if(type(radi) == int):
		if(mask_option is None):  mask = model_circle(radi,nnxo,nnxo,nnxo)
		else:                           mask = get_im(mask_option)
	else:  mask = radi
	nfsc = fsc(vol[0]*mask,vol[1]*mask, 1.0,os.path.join(fscoutputdir,"fsc.txt") )
	currentres = -1.0
	ns = len(nfsc[1])
	#  This is actual resolution, as computed by 2*f/(1+f)
	for i in xrange(1,ns-1):
		if ( nfsc[1][i] < 0.333333333333333333333333):
			currentres = nfsc[0][i-1]
			break
		if(currentres < 0.0):
			print("  Something wrong with the resolution, cannot continue")
		currentres = nfsc[0][i-1]
        
        """ this commented previously
		lowpass = 0.5
		ns = len(nfsc[1])
        #  This is resolution used to filter half-volumes
        for i in xrange(1,ns-1):
                if ( nfsc[1][i] < 0.5 ):
                        lowpass = nfsc[0][i-1]
                        break
        """  
	lowpass, falloff = fit_tanh1(nfsc, 0.01)
	return  round(lowpass,4), round(falloff,4), round(currentres,2)
        
def partition_to_groups(alist,K):
	res =[]
	for igroup in xrange(K):
		this_group =[]
		for imeb in xrange(len(alist)):
			if alist[imeb] ==igroup:
				this_group.append(imeb)
		this_group.sort()
		res.append(this_group)
	return res

def partition_independent_runs(run_list,K):
	indep_runs_groups={}
	for indep in xrange(len(run_list)):
		this_run = run_list[indep]
		groups = partition_to_groups(this_run,K)
		indep_runs_groups[indep]=groups 
	return indep_runs_groups

def get_outliers(total_number,plist):
	tlist={}
	for i in xrange(total_number):
		tlist[i]=i
	for a in plist:
		del tlist[a]
	out =[]
	for a in tlist:
		out.append(a)
	return out

def merge_groups(stable_members_list):
	alist=[]
	for i in xrange(len(stable_members_list)):
		for j in xrange(len(stable_members_list[i])):
			alist.append(stable_members_list[i][j])
	return alist

def save_alist(Tracker,name_of_the_text_file,alist):
	from utilities import write_text_file
	import os
	log       =Tracker["constants"]["log_main"]
	myid      =Tracker["constants"]["myid"]
	main_node =Tracker["constants"]["main_node"]
	dir_to_save_list =Tracker["this_dir"]
	if myid==main_node:
		file_name=os.path.join(dir_to_save_list,name_of_the_text_file)
		write_text_file(alist, file_name)
"""
def reconstruct_grouped_vols(Tracker,name_of_grouped_vols,grouped_plist):
	from mpi import  MPI_COMM_WORLD,mpi_barrier
	from applications import recons3d_n_MPI
	from utilities import cmdexecute
	import os
	myid		 = Tracker["constants"]["myid"]
	main_node	 = Tracker["constants"]["main_node"]
	main_dir         = Tracker["this_dir"]
	number_of_groups = Tracker["number_of_groups"]
	data_stack       = Tracker["this_data_stack"]
	log              = Tracker["constants"]["log_main"]
	####
	if myid ==main_node:
		log.add("Reconstruct a group of volumes")
	for igrp in xrange(number_of_groups):
		#pid_list=Tracker["two_way_stable_member"][igrp]
		pid_list =grouped_plist[igrp]
                vol_stack=os.path.join(main_dir,"TMP_init%03d.hdf"%igrp)
                tlist=[]
                for b in pid_list:
                	tlist.append(int(b))
                recons3d_n_MPI(data_stack,tlist,vol_stack,Tracker["constants"]["CTF"],Tracker["constants"]["snr"],\
                Tracker["constants"]["sign"],Tracker["constants"]["npad"],Tracker["constants"]["sym"], \
		Tracker["constants"]["listfile"],Tracker["constants"]["group"],\
                Tracker["constants"]["verbose"],Tracker["constants"]["xysize"],Tracker["constants"]["zsize"])
                newvols=os.path.join(main_dir,"TMP_init*.hdf")
        if myid==main_node:
       		#cmd ="{} {} {}".format("sxcpy.py",newvols,Tracker["EKKMREF"][inew]["refvols"]) # Make stacks
		cmd ="{} {} {}".format("sxcpy.py",newvols,name_of_grouped_vols)  
        	cmdexecute(cmd)
                cmd ="{} {}".format("rm",newvols)
                cmdexecute(cmd)
        mpi_barrier(MPI_COMM_WORLD)

def N_independent_reconstructions(Tracker):
	from applications import recons3d_n_MPI
	from utilities import write_text_file, read_text_file, cmdexecute
	import os
	from mpi import mpi_barrier,MPI_COMM_WORLD
	from random import shuffle
	myid      =Tracker["constants"]["myid"]
	main_node =Tracker["constants"]["main_node"]
	initdir   =Tracker["this_dir"]
	data_stack=Tracker["this_data_stack"]
	total_stack =Tracker["this_total_stack"] 
	log_main =Tracker["constants"]["log_main"]
	if myid ==main_node:
		log_main.add("-----------Independent reconstructions---------------")
        for irandom in xrange(Tracker["constants"]["indep_runs"]):
        	ll=range(total_stack)
                shuffle(ll)
                if myid ==main_node:
                	log_main.add("Initial random assignments     "+os.path.join(initdir,"random_list%d.txt"%irandom))
                        write_text_file(ll,os.path.join(initdir,"random_list%d.txt"%irandom))
                        log_main.add("preset ali3d_parameters ")
	mpi_barrier(MPI_COMM_WORLD)
	if myid ==main_node:
         	if Tracker["importali3d"]!="":
         		cmd = "{} {} {} {}".format("sxheader.py",data_stack,"--params=xform.projection", "--import="+ \
				Tracker["importali3d"])
                	cmdexecute(cmd)
			log_main.add("ali3d_parameters is preset to "+Tracker["importali3d"])
		else:
			log_main.add("ali3d parameters in this run are not altered !")
	for iter_indep in xrange(Tracker["constants"]["indep_runs"]):
       		ll=read_text_file(os.path.join(initdir,"random_list%d.txt"%iter_indep))
                linit_list =[]
                for igrp in xrange(Tracker["number_of_groups"]):
                       	alist=ll[(total_stack*igrp)//Tracker["number_of_groups"]:(total_stack*(igrp+1))//Tracker["number_of_groups"]]
                       	alist.sort()
                       	linit_list.append(alist)
                	linit_list_file_name=os.path.join(initdir,"list1_grp%0d_%0d.txt"%(igrp,iter_indep))
			if myid ==main_node:
                		write_text_file(alist,linit_list_file_name)
                       	volstack =os.path.join(initdir,"TMP_vol%03d.hdf"%igrp)
                       	recons3d_n_MPI(data_stack,alist,volstack,Tracker["constants"]["CTF"],Tracker["constants"]["snr"],Tracker["constants"]["sign"],\
                       	Tracker["constants"]["npad"],Tracker["constants"]["sym"],Tracker["constants"]["listfile"],Tracker["constants"]["group"],\
			Tracker["constants"]["verbose"],Tracker["constants"]["xysize"],Tracker["constants"]["zsize"])
                newvols=os.path.join(initdir,"TMP_vol*.hdf")
                computed_refvol_name=os.path.join(initdir,"vol_run_%03d.hdf"%iter_indep)
                filtered_volumes =os.path.join(initdir,"volf_run_%03d.hdf"%iter_indep)
                filter_options ="--process=filter.lowpass.tanh:cutoff_abs="+str(Tracker["low_pass"])+":fall_off=.1"
                if myid==main_node:
                       cmd ="{} {} {}".format("sxcpy.py",newvols,computed_refvol_name) # Make stacks 
                       cmdexecute(cmd)
                       cmd ="{} {}".format("rm",newvols)
                       cmdexecute(cmd)
                       cmd ="{}  {}  {} {}".format("e2proc3d.py",computed_refvol_name,filtered_volumes,filter_options)
                       cmdexecute(cmd)
		mpi_barrier(MPI_COMM_WORLD)

def N_independent_Kmref(mpi_comm,Tracker):
	from mpi import mpi_barrier,MPI_COMM_WORLD
	from applications import Kmref_ali3d_MPI
	from utilities import cmdexecute
	from logger import Logger,BaseLogger_Files
	myid            = Tracker["constants"]["myid"]
	main_node       = Tracker["constants"]["main_node"]
	log_main        = Tracker["constants"]["log_main"]
	data_stack      = Tracker["this_data_stack"]
	if myid ==main_node:
		log_main.add("-----------%5d independent runs of Kmref -----------------"%Tracker["constants"]["indep_runs"])
	for iter_indep in xrange(Tracker["constants"]["indep_runs"]):
        	log_Kmref       =Logger(BaseLogger_Files())
                log_Kmref.prefix=Tracker["KMREF"][iter_indep]["output_dir"]+"/"
                empty_group =Kmref_ali3d_MPI(data_stack,Tracker["KMREF"][iter_indep]["refvols"],Tracker["KMREF"][iter_indep]["output_dir"], \
		Tracker["constants"]["mask3D"],Tracker["constants"]["focus3Dmask"],Tracker["constants"]["maxit"],\
		Tracker["constants"]["ir"],Tracker["constants"]["radius"],Tracker["constants"]["rs"],\
                Tracker["constants"]["xr"],Tracker["constants"]["yr"],Tracker["constants"]["ts"],Tracker["constants"]["delta"],\
		Tracker["constants"]["nassign"],Tracker["constants"]["nrefine"],Tracker["constants"]["an"],Tracker["constants"]["center"],\
                Tracker["constants"]["CTF"],Tracker["constants"]["snr"],Tracker["constants"]["ref_a"],Tracker["constants"]["sym"],\
                Tracker["constants"]["user_func"],Tracker["constants"]["npad"],Tracker["constants"]["debug"],\
		Tracker["constants"]["fourvar"],Tracker["constants"]["stoprnct"],mpi_comm,log_Kmref)
                if myid==main_node:
                	cmd = "{} {} {} {}".format("sxheader.py",data_stack,"--params=group", \
					"--export="+Tracker["KMREF"][iter_indep]["partition"])
                	cmdexecute(cmd)
                mpi_barrier(MPI_COMM_WORLD)
	
def do_independent_EKmref(Tracker):
	from mpi import mpi_barrier,MPI_COMM_WORLD
	from applications import Kmref_ali3d_MPI
	from utilities import cmdexecute
	from logger import Logger,BaseLogger_Files
	myid            = Tracker["constants"]["myid"]
        main_node       = Tracker["constants"]["main_node"]
        log_main        = Tracker["constants"]["log_main"]
        data_stack      = Tracker["this_data_stack"]
	iruns           = Tracker["this_iruns"]
	for iter_indep in xrange(iruns):
		log_Kmref       =Logger(BaseLogger_Files())
		log_Kmref.prefix=Tracker["EKMREF"][iter_indep]["output_dir"]+"/"
		empty_group =Kmref_ali3d_MPI(data_stack,Tracker["EKMREF"][iter_indep]["refvols"],Tracker["EKMREF"][iter_indep]["output_dir"], \
                Tracker["constants"]["mask3D"],Tracker["constants"]["focus3Dmask"],Tracker["constants"]["maxit"],\
                Tracker["constants"]["ir"],Tracker["constants"]["radius"],Tracker["constants"]["rs"],\
                Tracker["constants"]["xr"],Tracker["constants"]["yr"],Tracker["constants"]["ts"],Tracker["constants"]["delta"],\
		Tracker["constants"]["an"],Tracker["constants"]["center"],\
                Tracker["constants"]["nassign"],Tracker["constants"]["nrefine"],\
                Tracker["constants"]["CTF"],Tracker["constants"]["snr"],Tracker["constants"]["ref_a"],Tracker["constants"]["sym"],\
                Tracker["constants"]["user_func"],Tracker["constants"]["npad"],Tracker["constants"]["debug"],\
                Tracker["constants"]["fourvar"],Tracker["constants"]["stoprnct"],Tracker["constants"]["mpi_comm"],log_Kmref)
                if myid==main_node:
                        cmd = "{} {} {} {}".format("sxheader.py",data_stack,"--params=group",\
					 "--export="+Tracker["EKMREF"][iter_indep]["partition"])
                        cmdexecute(cmd)
                mpi_barrier(MPI_COMM_WORLD)

def N_independent_mref(mpi_comm,Tracker):
	from mpi import mpi_barrier,MPI_COMM_WORLD
	from applications import mref_ali3d_MPI
	from utilities import cmdexecute
	from logger import Logger,BaseLogger_Files
	myid      = Tracker["constants"]["myid"]
	main_node = Tracker["constants"]["main_node"]
	log_main  = Tracker["constants"]["log_main"]
	data_stack= Tracker["this_data_stack"]
	if myid ==main_node:
        	log_main.add("-----------%5d independent runs of Equal Kmeans -----------------"%Tracker["constants"]["indep_runs"])
	for iter_indep in xrange(Tracker["constants"]["indep_runs"]):
		if myid==main_node:
			log_main.add(" %d th run  starts !  "%iter_indep)
        	outdir = Tracker["EMREF"][iter_indep]["output_dir"]
                #doit, keepchecking = checkstep(outdir, keepchecking, myid, main_node)
                log_Emref=Logger(BaseLogger_Files())
                log_Emref.prefix=outdir+"/"
                if Tracker["importali3d"]!="" and myid ==main_node:
                	cmd = "{} {} {} {}".format("sxheader.py",data_stack,"--params=xform.projection", \
				 "--import="+Tracker["importali3d"])
                        cmdexecute(cmd)
               	mpi_barrier(MPI_COMM_WORLD)
               	mref_ali3d_MPI_beta(data_stack,Tracker["EMREF"][iter_indep]["refvols"],outdir,Tracker["constants"]["mask3D"] ,\
               	Tracker["constants"]["focus3Dmask"],Tracker["constants"]["maxit"],Tracker["constants"]["ir"],\
		Tracker["constants"]["radius"],Tracker["constants"]["rs"],Tracker["constants"]["xr"],\
		Tracker["constants"]["yr"],Tracker["constants"]["ts"],\
               	Tracker["constants"]["delta"],Tracker["constants"]["an"],Tracker["constants"]["center"],\
		Tracker["constants"]["nassign"],Tracker["constants"]["nrefine"],\
               	Tracker["constants"]["CTF"],Tracker["constants"]["snr"],Tracker["constants"]["ref_a"],Tracker["constants"]["sym"],\
               	Tracker["constants"]["user_func"],Tracker["constants"]["npad"],Tracker["constants"]["debug"],\
		Tracker["constants"]["fourvar"],Tracker["constants"]["stoprnct"], mpi_comm,log_Emref,Tracker["frequency_low_pass"])
               	if myid==main_node:
             		cmd = "{} {} {} {}".format("sxheader.py",Tracker["this_data_stack"],"--params=group",\
			 "--export="+Tracker["EMREF"][iter_indep]["partition"])
                        cmdexecute(cmd)
                        if Tracker["constants"]["nrefine"] !=0:
                        	cmd = "{} {} {} {}".format("sxheader.py",Tracker["this_data_stack"],"--params=xform.projection",\
				 "--export="+Tracker["EMREF"][iter_indep]["ali3d"])
                        	cmdexecute(cmd)
		mpi_barrier(MPI_COMM_WORLD)

def prepare_EMREF_dict(Tracker):
	main_dir =Tracker["this_dir"]
	EMREF_iteration  ={}
        for iter_indep in xrange(Tracker["constants"]["indep_runs"]):
        	output_for_this_run ={}
        	output_for_this_run["output_dir"]= os.path.join(main_dir,"EMREF_independent_%03d"%iter_indep)
        	output_for_this_run["partition"] = os.path.join(output_for_this_run["output_dir"],"list2.txt")
        	output_for_this_run["refvols"]   = os.path.join(main_dir,"volf_run_%03d.hdf"%iter_indep)
        	output_for_this_run["ali3d"]     = os.path.join(output_for_this_run["output_dir"],"ali3d_params.txt")
        	EMREF_iteration[iter_indep]=output_for_this_run
        Tracker["EMREF"]=EMREF_iteration

def prepare_KMREF_dict(Tracker):
	main_dir =Tracker["this_dir"]
	KMREF_iteration  ={}
        for iter_indep in xrange(Tracker["constants"]["indep_runs"]):
        	output_for_this_run ={}
                output_for_this_run["output_dir"]= os.path.join(main_dir,"KMREF_independent_%03d"%iter_indep)
                output_for_this_run["partition"] = os.path.join(output_for_this_run["output_dir"],"list2.txt")
                output_for_this_run["refvols"]   = os.path.join(main_dir,"volf_run_%03d.hdf"%iter_indep)
                output_for_this_run["ali3d"]     = os.path.join(output_for_this_run["output_dir"],"ali3d_params.txt")
                KMREF_iteration[iter_indep]=output_for_this_run
        Tracker["KMREF"]=KMREF_iteration

def set_refvols_table(initdir,vol_pattern,Tracker):
	# vol_pattern="volf_run_%03d.hdf"; volf_stable_%3d.hdf
	import os
	initial_random_vol={}
        for iter_indep in xrange(Tracker["constants"]["indep_runs"]):
        	filtered_volumes =os.path.join(initdir,vol_pattern%iter_indep)
                initial_random_vol[iter_indep]=filtered_volumes
        Tracker["refvols"]=initial_random_vol

def prepare_EKMREF_dict(Tracker):
	main_dir = Tracker["this_dir"]
	KMREF_iteration  ={}
        for iter_indep in xrange(Tracker["constants"]["indep_runs"]):
        	output_for_this_run ={}
                output_for_this_run["output_dir"]=os.path.join(main_dir,"EKMREF%03d"%iter_indep)
                output_for_this_run["partition"] =os.path.join(output_for_this_run["output_dir"],"list2.txt")
                output_for_this_run["ali3d"]     = os.path.join(output_for_this_run["output_dir"],"ali3d_params.txt")
                KMREF_iteration[iter_indep]=output_for_this_run
        Tracker["EKMREF"]=KMREF_iteration
def partition_ali3d_params_of_outliers(Tracker):
	from utilities import read_text_file,write_text_file
	from mpi import mpi_barrier, MPI_COMM_WORLD
	myid 	   = Tracker["constants"]["myid"]
	main_node  = Tracker["constants"]["main_node"]
	outlier_list=read_text_file(Tracker["this_unaccounted"])
	accounted_list=read_text_file(Tracker["this_accounted"])
	ali3d_params_of_outliers = []
	ali3d_params_of_accounted  = []
	if Tracker["constants"]["importali3d"] !="":
		ali3d_params_of_outliers   = []
		ali3d_params_of_accounted  = []
		ali3d_params=read_text_file(Tracker["this_ali3d"])
		for i in xrange(len(outlier_list)):
			ali3d_params_of_outliers.append(ali3d_params[outlier_list[i]])
		if myid ==main_node:
			write_text_file(ali3d_params_of_outliers,Tracker["ali3d_of_outliers"])
		for i in xrange(len(accounted_list)):
			ali3d_params_of_accounted.append(ali3d_params[accounted_list[i]])
		if myid ==main_node:
			write_text_file(ali3d_params_of_accounted,Tracker["ali3d_of_accounted"])
	Tracker["number_of_unaccounted"]=len(outlier_list)
	Tracker["average_members_in_a_group"]= len(accounted_list)/float(Tracker["number_of_groups"])
	mpi_barrier(MPI_COMM_WORLD)
"""

def do_two_way_comparison(Tracker):
	from mpi import mpi_barrier, MPI_COMM_WORLD
	from utilities import read_text_file,write_text_file
	from statistics import k_means_match_clusters_asg_new
	######
	myid              =Tracker["constants"]["myid"]
	main_node         =Tracker["constants"]["main_node"]
	log_main          =Tracker["constants"]["log_main"]
	total_stack       =Tracker["this_total_stack"]
	main_dir          =Tracker["this_dir"]
	number_of_groups  =Tracker["number_of_groups"]
	######
	if myid ==main_node:
		msg="-------Two_way comparisons analysis of %3d independent runs of equal Kmeans-------"%Tracker["constants"]["indep_runs"]
		log_main.add(msg)
	total_partition=[]
	if Tracker["constants"]["indep_runs"]<2:
		if myid ==main_node:
			log_main.add(" Error! One single run cannot make two-way comparison")
		from mip import mpi_finalize
		mpi_finalize()
		exit()
	for iter_indep in xrange(Tracker["constants"]["indep_runs"]):
		partition_list=Tracker["partition_dict"][iter_indep]
		total_partition.append(partition_list)
    ### Two-way comparision is carried out on all nodes 
	ptp=prepare_ptp(total_partition,number_of_groups)
	indep_runs_to_groups =partition_independent_runs(total_partition,number_of_groups)
	total_pop=0
	two_ways_stable_member_list={}
	avg_two_ways               =0.0
	avg_two_ways_square        =0.
	scores                     ={}
	for iptp in xrange(len(ptp)):
		for jptp in xrange(len(ptp)):
			newindeces, list_stable, nb_tot_objs = k_means_match_clusters_asg_new(ptp[iptp],ptp[jptp])
			tt =0.
			if myid ==main_node and iptp<jptp:
				aline=print_a_line_with_timestamp("Two-way comparison between independent run %3d and %3d"%(iptp,jptp))
				log_main.add(aline)
			for m in xrange(len(list_stable)):
				a=list_stable[m]
				tt +=len(a)
				#if myid==main_node and iptp<jptp:
					#aline=print_a_line_with_timestamp("Group %d  number of stable members %10d  "%(m,len(a)))
					#log_main.add(aline)
					#aline=print_a_line_with_timestamp("The comparison is between %3d th group of %3d th run and %3d th group of %3d th run" \
					# 									%(newindeces[m][0],iptp,newindeces[m][1],jptp))
					#log_main.add(aline)
					#aline=print_a_line_with_timestamp("The  %3d th group of %3d th run contains %6d members" \
					#	        %(iptp,newindeces[m][0],len(indep_runs_to_groups[iptp][newindeces[m][0]])))
					#log_main.add(aline)
					#aline=print_a_line_with_timestamp("The  %3d th group of %3d th run contains %6d members"%(jptp,newindeces[m][1],\
					#			len(indep_runs_to_groups[jptp][newindeces[m][1]]))) 
			if myid==main_node and iptp<jptp:
				unaccounted=total_stack-tt
				ratio_unaccounted  = 100.-tt/total_stack*100.
				ratio_accounted    = tt/total_stack*100
				#aline             = print_a_line_with_timestamp("Accounted data is %6d, %5.2f "%(int(tt),ratio_accounted))
				#log_main.add(aline)
				#aline=print_a_line_with_timestamp("Unaccounted data is %6d, %5.2f"%(int(unaccounted),ratio_unaccounted))
				#log_main.add(aline)
			rate=tt/total_stack*100.0
			scores[(iptp,jptp)] =rate
			if iptp<jptp:
				avg_two_ways 	    +=rate
				avg_two_ways_square +=rate**2
				total_pop +=1
				#if myid ==main_node and iptp<jptp:
				#aline=print_a_line_with_timestamp("The two-way comparison stable member total ratio %3d %3d %5.3f  "%(iptp,jptp,rate))
				#log_main.add(aline)
				new_list=[]
				for a in list_stable:
					a.tolist()
					new_list.append(a)
				two_ways_stable_member_list[(iptp,jptp)]=new_list
	if myid ==main_node:
		log_main.add("two_way comparison is done!")
	#### Score each independent run by pairwise summation
	summed_scores =[]
	two_way_dict  ={}
	for ipp in xrange(len(ptp)):
		avg_scores =0.0
		for jpp in xrange(len(ptp)):
			if ipp!=jpp:
				avg_scores +=scores[(ipp,jpp)]
		avg_rate =avg_scores/(len(ptp)-1)
		summed_scores.append(avg_rate)
		two_way_dict[avg_rate] =ipp
	#### Select two independent runs that have the first two highest scores
	if Tracker["constants"]["indep_runs"]>2:
		rate1=max(summed_scores)
		run1 =two_way_dict[rate1]
		summed_scores.remove(rate1)
		rate2 =max(summed_scores)
		run2 = two_way_dict[rate2]
	else:
		run1 =0
		run2 =1
		rate1  =max(summed_scores)
		rate2  =rate1
	Tracker["two_way_stable_member"]      =two_ways_stable_member_list[(min(run1,run2),max(run1,run2))]
	Tracker["pop_size_of_stable_members"] =1
	if myid ==main_node:
		log_main.add("Get outliers of the selected comparison")
	####  Save both accounted ones and unaccounted ones
	counted_list = merge_groups(two_ways_stable_member_list[(min(run1,run2),max(run1,run2))])
	outliers     = get_outliers(total_stack,counted_list)
	if myid ==main_node:
		log_main.add("Save outliers")
	stable_class_list = []
	for istable in xrange(len(Tracker["two_way_stable_member"])):
		one_class = Tracker["two_way_stable_member"][istable]
		write_text_file(one_class, "class%d.txt"%istable)
		new_one_class, new_tmp_dict = get_initial_ID(one_class, Tracker["full_ID_dict"])
		write_text_file(new_one_class, "new_class%d.txt"%istable)
		stable_class_list.append(new_one_class) 
	Tracker["two_way_stable_member"] =  stable_class_list 
	outliers, new_dict1 = get_initial_ID(outliers, Tracker["full_ID_dict"])
	save_alist(Tracker,"Unaccounted.txt",outliers)
	Tracker["this_unaccounted_list"] =  outliers
	mpi_barrier(MPI_COMM_WORLD)
	accounted_list, new_dict2 = get_initial_ID(counted_list, Tracker["full_ID_dict"])
	Tracker["this_accounted_list"] = accounted_list
	save_alist(Tracker,"Accounted.txt",accounted_list)
	Tracker["full_ID_dict"] = new_dict1 ## Update full_ID_dict for the next generation
	mpi_barrier(MPI_COMM_WORLD)
	Tracker["this_unaccounted_dir"]     =main_dir
	Tracker["this_unaccounted_text"]    =os.path.join(main_dir,"Unaccounted.txt")
	Tracker["this_accounted_text"]      =os.path.join(main_dir,"Accounted.txt")
	Tracker["ali3d_of_outliers"]        =os.path.join(main_dir,"ali3d_params_of_outliers.txt")
	Tracker["ali3d_of_accounted"]       =os.path.join(main_dir, "ali3d_params_of_accounted.txt")
	if myid==main_node:
		log_main.add(" Selected indepedent runs      %5d and  %5d"%(run1,run2))
		log_main.add(" Their pair-wise averaged rates are %5.2f  and %5.2f "%(rate1,rate2))		
	from math import sqrt
	avg_two_ways = avg_two_ways/total_pop
	two_ways_std = sqrt(avg_two_ways_square/total_pop-avg_two_ways**2)
	net_rate     = avg_two_ways-1./number_of_groups*100.
	Tracker["net_rate"]=net_rate
	if myid ==main_node: 
		msg="average of two-way comparison  %5.3f"%avg_two_ways
		log_main.add(msg)
		msg="net rate of two-way comparison  %5.3f"%net_rate
		log_main.add(msg)
		msg="std of two-way comparison %5.3f"%two_ways_std
		log_main.add(msg)
		msg ="Score table of two_way comparison when Kgroup =  %5d"%number_of_groups
		log_main.add(msg)
		print_upper_triangular_matrix(scores,Tracker["constants"]["indep_runs"],log_main)
	del two_ways_stable_member_list
	Tracker["score_of_this_comparison"]=(avg_two_ways,two_ways_std,net_rate)
	mpi_barrier(MPI_COMM_WORLD)
"""	
def do_EKmref(Tracker):
	from mpi import mpi_barrier, MPI_COMM_WORLD
	from utilities import cmdexecute
	## Use stable members of only one two-way comparison
	main_dir  =Tracker["this_dir"]
	pop_size  =Tracker["pop_size_of_stable_members"]# Currently is 1, can be changed
	log_main  =Tracker["constants"]["log_main"]
	myid      =Tracker["constants"]["myid"]
	main_node =Tracker["constants"]["main_node"]
	import os
	###
	EKMREF_iteration ={}
	if myid ==main_node:
		log_main.add("-----------------EKmref---------------------------")
	for inew in xrange(1):# new independent run
        	output_for_this_run ={}
                output_for_this_run["output_dir"]=os.path.join(main_dir,"EKMREF%03d"%inew)
                output_for_this_run["partition"] =os.path.join(output_for_this_run["output_dir"],"list2.txt")
                output_for_this_run["refvols"]=os.path.join(main_dir,"vol_stable_member_%03d.hdf"%inew)
                EKMREF_iteration[inew]=output_for_this_run
        Tracker["EKMREF"]=EKMREF_iteration
        for inew in xrange(1):
        	if myid ==main_node:
                	msg="Create %dth two-way reference  model"%inew
                	log_main.add(msg)
                name_of_grouped_vols=Tracker["EKMREF"][inew]["refvols"]
                #Tracker["this_data_stack"] =Tracker["constants"]["stack"]
                grouped_plist=Tracker["two_way_stable_member"]
                reconstruct_grouped_vols(Tracker,name_of_grouped_vols,grouped_plist)
	########
	Tracker["this_iruns"]=1
	Tracker["data_stack_of_accounted"]="bdb:"+os.path.join(Tracker["this_dir"],"accounted")
	partition_ali3d_params_of_outliers(Tracker)
	if myid==main_node:
		cmd = "{} {} {} {} {}".format("e2bdb.py",Tracker["this_data_stack"],"--makevstack",\
			Tracker["data_stack_of_accounted"],"--list="+Tracker["this_accounted"])
       		cmdexecute(cmd)
		#cmd = "{} {} {} {}  {}".format("sxheader.py", Tracker["data_stack_of_counted"],"--params=xform.projection",\
		#		 "--import="+Tracker["ali3d_of_counted"], "--consecutive ")
		#cmdexecute(cmd)
	mpi_barrier(MPI_COMM_WORLD)
	Tracker["this_data_stack"]=Tracker["data_stack_of_accounted"]
	do_independent_EKmref(Tracker)

def Kgroup_guess(Tracker,data_stack):
	myid      = Tracker["constants"]["myid"]
	main_node = Tracker["constants"]["main_node"]
	log_main  = Tracker["constants"]["log_main"]
	if myid==main_node:
		msg="Program Kgroup_guess"
		log_main.add(msg)
		msg="Estimate how many groups the dataset can be partitioned into"
		log_main.add(msg)
	number_of_groups=2
	Tracker["this_data_stack"]=data_stack
	maindir                   =Tracker["this_dir"]
	terminate                 =0
	while terminate !=1:
		do_EKTC_for_a_given_number_of_groups(Tracker,number_of_groups)
		(score_this, score_std_this, score_net)=Tracker["score_of_this_comparison"]
		number_of_groups +=1
		if number_of_groups >10:
			terminate  =1
def do_N_groups(Tracker,data_stack):
	myid      = Tracker["constants"]["myid"]
        main_node = Tracker["constants"]["main_node"]
        log_main  = Tracker["constants"]["log_main"]
        if myid==main_node:
                msg="Program do_N_groups"
                log_main.add(msg)
                msg="Estimate how many groups the dataset can be partitioned into"
                log_main.add(msg)
        Tracker["this_data_stack"]=data_stack
        maindir                   =Tracker["this_dir"]
	number_of_groups          =Tracker["number_of_groups"]
	for Ngroup in xrange(2,number_of_groups+1):
		Tracker["this_data_stack"]=data_stack
		Tracker["this_dir"]       =maindir
		Tracker["number_of_groups"]=Ngroup
		do_EKTC_for_a_given_number_of_groups(Tracker,Ngroup)
                (score_this, score_std_this, score_net)=Tracker["score_of_this_comparison"]
		Tracker["this_dir"]       =os.path.join(maindir,"GRP%03d"%Tracker["number_of_groups"])
		do_EKmref(Tracker)

def do_EKTC_for_a_given_number_of_groups(Tracker,given_number_of_groups):
	import os
	from utilities import cmdexecute
	Tracker["number_of_groups"]= given_number_of_groups
	from mpi import mpi_barrier,MPI_COMM_WORLD
	log_main  = Tracker["constants"]["log_main"]
	myid      = Tracker["constants"]["myid"]
	main_node = Tracker["constants"]["main_node"]
	maindir   = Tracker["this_dir"]
	workdir   = os.path.join(maindir,"GRP%03d"%Tracker["number_of_groups"])
	if myid ==main_node:
		msg ="Number of group is %5d"%given_number_of_groups
		log_main.add(msg)
 		cmd="{} {}".format("mkdir",workdir)
        	cmdexecute(cmd)
	mpi_barrier(MPI_COMM_WORLD)
	Tracker["this_dir"]=workdir
	N_independent_reconstructions(Tracker)
	prepare_EMREF_dict(Tracker)
	N_independent_mref(Tracker["constants"]["mpi_comm"],Tracker)
	do_two_way_comparison(Tracker)
	Tracker["this_dir"]=maindir # always reset maindir

def do_EKTC_for_a_large_number_RUN(Tracker):
        import os
        from utilities import cmdexecute
        Tracker["number_of_groups"]=Tracker["constants"]["Kgroup"] 
        from mpi import mpi_barrier,MPI_COMM_WORLD
        log_main  = Tracker["constants"]["log_main"]
        myid      = Tracker["constants"]["myid"]
        main_node = Tracker["constants"]["main_node"]
        N_independent_reconstructions(Tracker)
        prepare_EMREF_dict(Tracker)
        N_independent_mref(Tracker["constants"]["mpi_comm"],Tracker)
        do_two_way_comparison(Tracker)

def low_pass_filter_search(Tracker):
        import os
        from utilities import cmdexecute,write_text_file
        from mpi import mpi_barrier,MPI_COMM_WORLD
	from logger import Logger, BaseLogger_Files
        log_main                   = Tracker["constants"]["log_main"]
        myid                       = Tracker["constants"]["myid"]
        main_node                  = Tracker["constants"]["main_node"]
        maindir                    = Tracker["this_dir"]
	number_of_groups           = Tracker["number_of_groups"]
	frequency_start_search     = Tracker["constants"]["frequency_start_search"]
	frequency_stop_search      = Tracker["constants"]["frequency_stop_search"]
	frequency_search_step      = Tracker["constants"]["frequency_search_step"]
	N_steps                    = int((frequency_stop_search-frequency_start_search)/frequency_search_step)
	search_result              = []
	log_lpfsearch              =Logger(BaseLogger_Files())
        log_lpfsearch.prefix=maindir+"/"
	if myid ==main_node:
		log_lpfsearch.add(" program low_pass_filter_search  ")
		log_lpfsearch.add(" start frequency is %5.3f"%frequency_start_search)
		log_lpfsearch.add(" stop frequency is %5.3f"%frequency_stop_search)
		log_lpfsearch.add(" search step is %5.3f"%frequency_search_step)
		log_lpfsearch.add(" total iteration is %5d"%N_steps)
	for iter_lpf in xrange(N_steps):
		frequency_low_pass           =frequency_start_search + iter_lpf*frequency_search_step
		Tracker["frequency_low_pass"]=frequency_low_pass 
		workdir                      =os.path.join(maindir,"lpf"+str(frequency_low_pass)) 
        	if myid == main_node:
                	msg ="the low-pass filter applied frequency is %5.3f"%frequency_low_pass
                	log_lpfsearch.add(msg)
                	cmd="{} {}".format("mkdir",workdir)
                	cmdexecute(cmd)
        	mpi_barrier(MPI_COMM_WORLD)
        	Tracker["this_dir"]=workdir
        	N_independent_reconstructions(Tracker)
        	prepare_EMREF_dict(Tracker)
        	N_independent_mref(Tracker["constants"]["mpi_comm"],Tracker)
        	do_two_way_comparison(Tracker)
		net_rate = Tracker["net_rate"]
		search_result.append([net_rate,frequency_low_pass])
		if myid ==main_node:
                	msg =" frequency  %5.3f   net rate  %5.3f "%(frequency_low_pass,net_rate)
                        log_lpfsearch.add(msg)
		mpi_barrier(MPI_COMM_WORLD)
	if myid ==main_node:
		write_text_file(search_result,os.path.join(maindir, "lpf_group%03d.txt"%number_of_groups))

def isac_3d(Tracker):
	import os
        from utilities import cmdexecute,write_text_file
        from mpi import mpi_barrier,MPI_COMM_WORLD
        from logger import Logger, BaseLogger_Files
        log_main                   = Tracker["constants"]["log_main"]
        myid                       = Tracker["constants"]["myid"]
        main_node                  = Tracker["constants"]["main_node"]
        maindir                    = Tracker["this_dir"]
        number_of_images_per_group = Tracker["constants"]["number_of_images_per_group"]
        log_isac_3d                = Logger(BaseLogger_Files())
        log_isac_3d.prefix= maindir+"/"
def get_shrink_data(Tracker):
	# The function will read from stack a subset of images specified in partids
	#   and assign to them parameters from partstack with optional CTF application and shifting of the data.
	# So, the lengths of partids and partstack are the same.
	#  The read data is properly distributed among MPI threads.
	from utilities    import read_text_file,wrap_mpi_bcast,read_text_row,model_circle,get_im,set_params_proj
	from filter       import filt_ctf
	from fundamentals import resample,fshift
	from applications import MPI_start_end
	from mpi import mpi_barrier, MPI_COMM_WORLD
	###
	myid       = Tracker["constants"]["myid"]
	main_node  = Tracker["constants"]["main_node"]
	nproc      = Tracker["constants"]["nproc"]
	nxinit     = Tracker["nxinit"]
	lpartids   = Tracker["this_data_list"] ## this is the only criritical input
	partstack  = Tracker["constants"]["ali3d"]
	preshift   = False
	###
	if( myid == main_node ):
		print("    ")
		line = strftime("%Y-%m-%d_%H:%M:%S", localtime()) + " =>"
		print(  line, "Reading data  onx: %3d, nx: %3d, CTF: %s, applyctf: %s, preshift: %s."%(Tracker["constants"]["nnxo"], nxinit, Tracker["constants"]["CTF"], Tracker["applyctf"], preshift) )
		print("                       stack:      %s\n                        partstack: %s\n"%(Tracker["constants"]["stack"],  partstack) )
	ndata = len(lpartids)
	if( myid == main_node ):  partstack = get_ali3d_params(partstack,lpartids)
	else:  partstack = 0
	partstack = wrap_mpi_bcast(partstack, main_node)
	if( ndata < nproc):
		if(myid<ndata):
			image_start = myid
			image_end   = myid+1
		else:
			image_start = 0
			image_end   = 1
	else:
		image_start, image_end = MPI_start_end(ndata, nproc, myid)
	lpartids  = lpartids[image_start:image_end]
	partstack = partstack[image_start:image_end]
	#  Preprocess the data
	mask2D  = model_circle(Tracker["constants"]["radius"],Tracker["constants"]["nnxo"],Tracker["constants"]["nnxo"])
	nima = image_end - image_start
	oldshifts = [[0.0,0.0]]#*nima
	data = [None]*nima
	shrinkage = nxinit/float(Tracker["constants"]["nnxo"])
	radius = int(Tracker["constants"]["radius"] * shrinkage +0.5)
	Tracker["this_radius"] = radius
	Tracker["shrinkage"]   = shrinkage
	#  Note these are in Fortran notation for polar searches
	#txm = float(nxinit-(nxinit//2+1) - radius -1)
	#txl = float(2 + radius - nxinit//2+1)
	txm = float(nxinit-(nxinit//2+1) - radius)
	txl = float(radius - nxinit//2+1)
	if Tracker["constants"]["CTF"]:
		from utilities import get_ctf, set_ctf
	for im in xrange(nima):
		data[im] = get_im(Tracker["constants"]["stack"],lpartids[im])
		st = Util.infomask(data[im], mask2D, False)
		data[im] -= st[0]
		phi,theta,psi,sx,sy = partstack[im][0], partstack[im][1], partstack[im][2], partstack[im][3], partstack[im][4]
		if( Tracker["constants"]["CTF"]):
			if Tracker["applyctf"]:
				ctf_params = data[im].get_attr("ctf")
				data[im] = filt_ctf(data[im], ctf_params)
				data[im].set_attr('ctf_applied', 1)
			else: # reset CTF when pixel size was changed
				defocus,cs,voltage,apix,bfactor,ampcont,dfdiff,dfang = get_ctf(data[im])
				apix =apix/shrinkage
				p = [defocus,cs,voltage,apix,bfactor,ampcont,dfdiff,dfang]
				#set_ctf(data[im],p)
		if preshift:
			data[im] = fshift(data[im], sx, sy)
			set_params_proj(data[im],[phi,theta,psi,0.0,0.0])
			#oldshifts[im] = [sx,sy]
			#  resample will properly adjusts shifts and pixel size in ctf
		data[im] = resample(data[im],shrinkage)
		#  We have to make sure the shifts are within correct range, shrinkage or not
		if Tracker["constants"]["CTF"] and Tracker["applyctf"] is False:
			set_ctf(data[im],p)
		set_params_proj(data[im],[phi,theta,psi,max(min(sx*shrinkage,txm),txl),max(min(sy*shrinkage,txm),txl)])
		#  For local SHC set anchor
		#if(nsoft == 1 and an[0] > -1):
		#  We will always set it to simplify the code
		set_params_proj(data[im],[phi,theta,psi,0.0,0.0], "xform.anchor")
	assert( nxinit == data[0].get_xsize() )  #  Just to make sure.
	#oldshifts = wrap_mpi_gatherv(oldshifts, main_node, MPI_COMM_WORLD)
	return data, oldshifts

def reconstruct_3D(Tracker,prjlist):
	from reconstruction import recons3d_4nn_ctf_MPI, recons3d_4nn_MPI
	#if Tracker["constants"]["CTF"] :
	vol = recons3d_4nn_ctf_MPI(myid=Tracker["constants"]["myid"], prjlist = prjlist,snr=1.0, sign=1, symmetry=Tracker["constants"]["sym"], info=None, npad=2)
        #else:   vol = recons3d_4nn_MPI(myid, prjlist, sym, finfo, npad, xysize, zsize)
	return vol
"""
def get_ali3d_params(ali3d_old_text_file,shuffled_list):
	from utilities import read_text_row
	ali3d_old = read_text_row(ali3d_old_text_file)
	ali3d_new = []
	for iptl in xrange(len(shuffled_list)):
		ali3d_new.append(ali3d_old[shuffled_list[iptl]])
	return ali3d_new

def counting_projections(delta,ali3d_params,image_start):
	from utilities import even_angles,angle_between_projections_directions
	sampled_directions = {}
	angles=even_angles(delta,0,180)
	for a in angles:
		[phi0, theta0, psi0]=a
		sampled_directions[(phi0,theta0)]=[]
	from math import sqrt
	for i in xrange(len(ali3d_params)):
		[phi, theta, psi, s2x, s2y] = ali3d_params[i]
		dis_min    = 9999.
		this_phi   = 9999.
		this_theta = 9999.
		this_psi   = 9999.
		prj1       =[phi,theta]
		for j in xrange(len(angles)):
			[phi0, theta0, psi0] = angles[j]
			prj2 =[phi0,theta0]
			dis=angle_between_projections_directions(prj1, prj2)
			if dis<dis_min:
				dis_min    =dis
				this_phi   =phi0
				this_theta =theta0
				this_psi   =psi0
		alist= sampled_directions[(this_phi,this_theta)]
		alist.append(i+image_start)
		sampled_directions[(this_phi,this_theta)]=alist
	return sampled_directions

def unload_dict(dict_angles):
	dlist =[]
	for a in dict_angles:
		tmp=[a[0],a[1]]
		tmp_list=dict_angles[a]
		for b in tmp_list:
			tmp.append(b)
		dlist.append(tmp)
	return dlist

def load_dict(dict_angle_main_node, unloaded_dict_angles):
	for ang_proj in unloaded_dict_angles:
		if len(ang_proj)>2:
			for item in xrange(2,len(ang_proj)):
				dict_angle_main_node[(ang_proj[0],ang_proj[1])].append(item)
	return dict_angle_main_node

def get_stat_proj(Tracker,delta,this_ali3d):
	from mpi import mpi_barrier, MPI_COMM_WORLD
	from utilities import read_text_row,wrap_mpi_bcast,even_angles
	from applications import MPI_start_end
	myid      = Tracker["constants"]["myid"]
	main_node = Tracker["constants"]["main_node"]
	nproc     = Tracker["constants"]["nproc"]
	mpi_comm  = MPI_COMM_WORLD
	if myid ==main_node:
		ali3d_params=read_text_row(this_ali3d)
		lpartids    = range(len(ali3d_params))
	else:
		lpartids      = 0
		ali3d_params  = 0
	lpartids = wrap_mpi_bcast(lpartids, main_node)
	ali3d_params = wrap_mpi_bcast(ali3d_params, main_node)
	ndata=len(ali3d_params)
	image_start, image_end = MPI_start_end(ndata, nproc, myid)
	ali3d_params=ali3d_params[image_start:image_end]
	sampled=counting_projections(delta,ali3d_params,image_start)
	for inode in xrange(nproc):
		if myid ==inode:
			dlist=unload_dict(sampled)
		else:
			dlist =0
		dlist=wrap_mpi_bcast(dlist,inode)
		if myid ==main_node and inode != main_node:
			sampled=load_dict(sampled,dlist)
		mpi_barrier(MPI_COMM_WORLD)
	return sampled

def get_attr_stack(data_stack,attr_string):
	attr_value_list = []
	for idat in xrange(len(data_stack)):
		attr_value = data_stack[idat].get_attr(attr_string)
		attr_value_list.append(attr_value)
	return attr_value_list

def fill_in_mpi_list(mpi_list,data_list,index_start,index_end):
	for index in xrange(index_start, index_end):
		mpi_list[index] = data_list[index-index_start]
	return mpi_list
	
def get_sorting_params(Tracker,data):
	from mpi import mpi_barrier, MPI_COMM_WORLD
	from utilities import read_text_row,wrap_mpi_bcast,even_angles
	from applications import MPI_start_end
	myid      = Tracker["constants"]["myid"]
	main_node = Tracker["constants"]["main_node"]
	nproc     = Tracker["constants"]["nproc"]
	ndata     = Tracker["total_stack"]
	mpi_comm  = MPI_COMM_WORLD
	if myid == main_node:
		total_attr_value_list = []
		for n in xrange(ndata):
			total_attr_value_list.append([])
	else:
		total_attr_value_list = 0
	for inode in xrange(nproc):
		attr_value_list =get_attr_stack(data,"group")
		attr_value_list =wrap_mpi_bcast(attr_value_list,inode)
		if myid ==main_node:
			image_start,image_end=MPI_start_end(ndata,nproc,inode)
			total_attr_value_list=fill_in_mpi_list(total_attr_value_list,attr_value_list,image_start,image_end)		
		mpi_barrier(MPI_COMM_WORLD)
	total_attr_value_list = wrap_mpi_bcast(total_attr_value_list,main_node)
	return total_attr_value_list
		
def create_random_list(Tracker):
	from random import shuffle
	myid        = Tracker["constants"]["myid"]
	main_node   = Tracker["constants"]["main_node"]
	total_stack = Tracker["total_stack"]
	from utilities import wrap_mpi_bcast
	indep_list  =[]
	import copy
	for irandom in xrange(Tracker["constants"]["indep_runs"]):
		ll=copy.copy(Tracker["this_data_list"])
		shuffle(ll)
		ll = wrap_mpi_bcast(ll, main_node)
		indep_list.append(ll)
	Tracker["this_indep_list"]=indep_list

def recons_mref(Tracker):
	from mpi import mpi_barrier, MPI_COMM_WORLD
	myid             = Tracker["constants"]["myid"]
	main_node        = Tracker["constants"]["main_node"]
	nproc            = Tracker["constants"]["nproc"]
	number_of_groups = Tracker["number_of_groups"]
	particle_list    = Tracker["this_particle_list"]
	nxinit           = Tracker["nxinit"]
	partstack        = Tracker["constants"]["partstack"]
	total_data       = len(particle_list)
	ref_list = []
	for igrp in xrange(number_of_groups):
		a_group_list=particle_list[(total_data*igrp)//number_of_groups:(total_data*(igrp+1))//number_of_groups]
		a_group_list.sort()
		Tracker["this_data_list"] = a_group_list
		from utilities import write_text_file
		particle_list_file = os.path.join(Tracker["this_dir"],"iclass%d.txt"%igrp)
		if myid ==main_node:
			write_text_file(Tracker["this_data_list"],particle_list_file)
		mpi_barrier(MPI_COMM_WORLD)
		data, old_shifts =  get_shrink_data_huang(Tracker,nxinit,particle_list_file,partstack,myid,main_node,nproc,preshift=True)
		#vol=reconstruct_3D(Tracker,data)
		mpi_barrier(MPI_COMM_WORLD)
		vol = recons3d_4nn_ctf_MPI(myid=myid,prjlist=data,symmetry=Tracker["constants"]["sym"],info=None)
		if myid ==main_node:
			print "reconstructed %3d"%igrp
		ref_list.append(vol)
	return ref_list

def apply_low_pass_filter(refvol,Tracker):
	from filter import filt_btwl
	for iref in xrange(len(refvol)):
		refvol[iref]=filt_btwl(refvol[iref],Tracker["frequency_low_pass"],Tracker["frequency_low_pass"]+.5)
	return refvol
	
def get_groups_from_partition(partition, initial_ID_list, number_of_groups):
	# sort out Kmref results to individual groups that has initial IDs
	# make a dictionary
	dict = {}
	for iptl in xrange(len(initial_ID_list)):
		dict[iptl] = initial_ID_list[iptl]
	res = []
	for igrp in xrange(number_of_groups):
		class_one = []
		for ipt in xrange(len(partition)):
			if partition[ipt] == igrp:
				orginal_id = dict[ipt]
				class_one.append(orginal_id)
		res.append(class_one)
	return res
				
def main():
	from logger import Logger, BaseLogger_Files
        arglist = []
        i = 0
        while( i < len(sys.argv) ):
            if sys.argv[i]=='-p4pg':
                i = i+2
            elif sys.argv[i]=='-p4wd':
                i = i+2
            else:
                arglist.append( sys.argv[i] )
                i = i+1
	progname = os.path.basename(arglist[0])
	usage = progname + " stack  outdir  <mask> --focus=3Dmask --ir=inner_radius --radius=outer_radius --rs=ring_step --xr=x_range --yr=y_range  --ts=translational_searching_step " +\
	" --delta=angular_step --an=angular_neighborhood --center=1 --nassign=reassignment_number --nrefine=alignment_number --maxit=max_iter --stoprnct=percentage_to_stop " + \
	" --CTF --snr=1.0 --ref_a=S --sym=c1 --function=user_function --independent=indenpendent_runs  --number_of_images_per_group=number_of_images_per_group  --resolution  "
	parser = OptionParser(usage,version=SPARXVERSION)
	parser.add_option("--focus",    type="string",       default=None,             help="3D mask for focused clustering ")
	parser.add_option("--ir",       type= "int",         default=1, 	       help="inner radius for rotational correlation > 0 (set to 1)")
	parser.add_option("--radius",   type= "int",         default="-1",	       help="outer radius for rotational correlation <nx-1 (set to the radius of the particle)")
	parser.add_option("--maxit",	type= "int",         default=5, 	       help="maximum number of iteration")
	parser.add_option("--rs",       type= "int",         default="1",	       help="step between rings in rotational correlation >0 (set to 1)" ) 
	parser.add_option("--xr",       type="string",       default="4 2 1 1 1",      help="range for translation search in x direction, search is +/-xr ")
	parser.add_option("--yr",       type="string",       default="-1",	       help="range for translation search in y direction, search is +/-yr (default = same as xr)")
	parser.add_option("--ts",       type="string",       default="0.25",           help="step size of the translation search in both directions direction, search is -xr, -xr+ts, 0, xr-ts, xr ")
	parser.add_option("--delta",    type="string",       default="10 6 4  3   2",  help="angular step of reference projections")
	parser.add_option("--an",       type="string",       default="-1",	       help="angular neighborhood for local searches")
	parser.add_option("--center",   type="int",          default=0,	               help="0 - if you do not want the volume to be centered, 1 - center the volume using cog (default=0)")
	parser.add_option("--nassign",  type="int",          default=0, 	       help="number of reassignment iterations performed for each angular step (set to 3) ")
	parser.add_option("--nrefine",  type="int",          default=1, 	       help="number of alignment iterations performed for each angular step (set to 1) ")
	parser.add_option("--CTF",      action="store_true", default=False,            help="Consider CTF correction during the alignment ")
	parser.add_option("--snr",      type="float",        default=1.0,              help="Signal-to-Noise Ratio of the data")   
	parser.add_option("--stoprnct", type="float",        default=0.0,              help="Minimum percentage of assignment change to stop the program")   
	parser.add_option("--ref_a",    type="string",       default="S",              help="method for generating the quasi-uniformly distributed projection directions (default S) ")
	parser.add_option("--sym",      type="string",       default="c1",             help="symmetry of the structure ")
	parser.add_option("--function", type="string",       default="ref_ali3dm",     help="name of the reference preparation function")
	parser.add_option("--npad",     type="int",          default= 2,               help="padding size for 3D reconstruction")
	parser.add_option("--independent", type="int",       default= 3,               help="number of independent run")
	parser.add_option("--number_of_images_per_group",    type="int",               default=-1,               help="number of groups")
	parser.add_option("--resolution",  type="float",     default= .40,             help="structure is low-pass-filtered to this resolution for clustering" )
	parser.add_option("--mode",        type="string",    default="EK_only",        help="mode options: EK_only, Kgroup_guess, auto_search, lpf_search,large_number_run,isac" )
	#parser.add_option("--importali3d", type="string",    default="",               help="import the xform.projection parameters as the initial configuration for 3-D reconstruction" )
	#parser.add_option("--Kgroup_guess",  action="store_true",default=False,        help="Guess the possible number of groups existing in one dataset" )
	#parser.add_option("--frequency_start_search",  type="float",default=.10,       help="start frequency for low pass filter search")
	#parser.add_option("--frequency_stop_search",   type="float",default=.40,       help="stop frequency for low pass filter search")
	#parser.add_option("--frequency_search_step",   type="float",default=.02,       help="frequency step for low pass filter search")
	parser.add_option("--scale_of_number", type="float",default=1.,                 help="scale number to control particle number per group")
	(options, args) = parser.parse_args(arglist[1:])
	if len(args) < 1  or len(args) > 4:
    		print "usage: " + usage
    		print "Please run '" + progname + " -h' for detailed options"
	else:

		if len(args)>2:
			mask_file = args[2]
		else:
			mask_file = None

		orgstack                        =args[0]
		masterdir                       =args[1]
		global_def.BATCH = True
		#---initialize MPI related variables
		from mpi import mpi_init, mpi_comm_size, MPI_COMM_WORLD, mpi_comm_rank,mpi_barrier,mpi_bcast, mpi_bcast, MPI_INT
		sys.argv = mpi_init(len(sys.argv),sys.argv)
		nproc     = mpi_comm_size(MPI_COMM_WORLD)
		myid      = mpi_comm_rank(MPI_COMM_WORLD)
		mpi_comm = MPI_COMM_WORLD
		main_node = 0
		# import some utilites
		from utilities import get_im,bcast_number_to_all,cmdexecute,write_text_file,read_text_file,wrap_mpi_bcast
		from applications import recons3d_n_MPI, mref_ali3d_MPI, Kmref_ali3d_MPI
		from statistics import k_means_match_clusters_asg_new,k_means_stab_bbenum 
		# Create the main log file
		from logger import Logger,BaseLogger_Files
		if myid ==main_node:
			log_main=Logger(BaseLogger_Files())
			log_main.prefix=masterdir+"/"
		else:
			log_main =None
		#--- fill input parameters into dictionary named after Constants
		Constants		         ={}
		Constants["stack"]               = args[0]
		Constants["masterdir"]           = masterdir
		Constants["mask3D"]              = mask_file
		Constants["focus3Dmask"]         = options.focus
		Constants["indep_runs"]          = options.independent
		Constants["stoprnct"]            = options.stoprnct
		Constants["number_of_images_per_group"]  = options.number_of_images_per_group
		Constants["CTF"]                 = options.CTF
		Constants["npad"]                = options.npad
		Constants["maxit"]               = options.maxit
		Constants["ir"]                  = options.ir 
		Constants["radius"]              = options.radius 
		Constants["nassign"]             = options.nassign
		Constants["snr"]                 = options.snr
		Constants["rs"]                  = options.rs 
		Constants["xr"]                  = options.xr
		Constants["yr"]                  = options.yr
		Constants["ts"]                  = options.ts
		Constants["ref_a"]               = options.ref_a
		Constants["delta"]               = options.delta
		Constants["an"]                  = options.an
		Constants["sym"]                 = options.sym
		Constants["center"]              = options.center
		Constants["nrefine"]             = options.nrefine
		#Constants["fourvar"]             = options.fourvar 
		Constants["user_func"]           = options.function
		Constants["resolution"]          = options.resolution
		#Constants["debug"]               = options.debug
		Constants["sign"]                = 1
		Constants["listfile"]            = ""
		Constants["xysize"]              =-1
		Constants["zsize"]               =-1
		Constants["group"]               =-1
		Constants["verbose"]             = 0
		Constants["mode"]                = options.mode
		#Constants["mpi_comm"]            = mpi_comm
		Constants["main_log_prefix"]     =args[1]
		#Constants["importali3d"]         =options.importali3d
		Constants["myid"]	         = myid
		Constants["main_node"]           =main_node
		Constants["nproc"]               =nproc
		Constants["log_main"]            =log_main
		#Constants["frequency_search_step"] = options.frequency_search_step
		#Constants["frequency_start_search"] = options.frequency_start_search
		#Constants["frequency_stop_search"] = options.frequency_stop_search
		Constants["scale_of_number"]    = options.scale_of_number
		# -----------------------------------------------------
		#
		# Create and initialize Tracker dictionary with input options
		Tracker = 			    		{}
		Tracker["constants"]=				Constants
		Tracker["maxit"]          = Tracker["constants"]["maxit"]
		Tracker["radius"]         = Tracker["constants"]["radius"]
		Tracker["xr"]             = ""
		Tracker["yr"]             = "-1"  # Do not change!
		Tracker["ts"]             = 1
		Tracker["an"]             = "-1"
		Tracker["delta"]          = "2.0"
		Tracker["zoom"]           = True
		Tracker["nsoft"]          = 0
		Tracker["local"]          = False
		Tracker["PWadjustment"]   = ""
		Tracker["upscale"]        = 0.5
		Tracker["applyctf"]       = False  #  Should the data be premultiplied by the CTF.  Set to False for local continuous.
		#Tracker["refvol"]         = None
		Tracker["nxinit"]         = 64
		Tracker["nxstep"]         = 32
		Tracker["icurrentres"]    = -1
		Tracker["ireachedres"]    = -1
		Tracker["lowpass"]        = 0.4
		Tracker["falloff"]        = 0.2
		#Tracker["inires"]         = options.inires  # Now in A, convert to absolute before using
		Tracker["fuse_freq"]      = 50  # Now in A, convert to absolute before using
		Tracker["delpreviousmax"] = False
		Tracker["anger"]          = -1.0
		Tracker["shifter"]        = -1.0
		Tracker["saturatecrit"]   = 0.95
		Tracker["pixercutoff"]    = 2.0
		Tracker["directory"]      = ""
		Tracker["previousoutputdir"] = ""
		#Tracker["eliminated-outliers"] = False
		Tracker["mainiteration"]  = 0
		Tracker["movedback"]      = False
		#Tracker["state"]          = Tracker["constants"]["states"][0] 
		Tracker["global_resolution"] =0.0
		Tracker["orgstack"]        = orgstack
		#--------------------------------------------------------------------
		#
		# Get the pixel size; if none, set to 1.0, and the original image size
		from utilities import get_shrink_data_huang
		if(myid == main_node):
			line = strftime("%Y-%m-%d_%H:%M:%S", localtime()) + " =>"
			print(line,"INITIALIZATION OF Equal-Kmeans & Kmeans Clustering")
			a = get_im(orgstack)
			nnxo = a.get_xsize()
			if( Tracker["nxinit"] > nnxo ):
				ERROR("Image size less than minimum permitted $d"%Tracker["nxinit"],"sxEKclustering",1)
				nnxo = -1
			else:
				if Tracker["constants"]["CTF"]:
					i = a.get_attr('ctf')
					pixel_size = i.apix
					fq = pixel_size/Tracker["fuse_freq"]
				else:
					pixel_size = 1.0
					#  No pixel size, fusing computed as 5 Fourier pixels
					fq = 5.0/nnxo
					del a
		else:
			nnxo = 0
			fq = 0.0
			pixel_size = 1.0
		nnxo = bcast_number_to_all(nnxo, source_node = main_node)
		if( nnxo < 0 ):
			mpi_finalize()
			exit()
		pixel_size = bcast_number_to_all(pixel_size, source_node = main_node)
		fq         = bcast_number_to_all(fq, source_node = main_node)
		Tracker["constants"]["nnxo"]         = nnxo
		Tracker["constants"]["pixel_size"]   = pixel_size
		Tracker["fuse_freq"]    = fq
		del fq, nnxo, pixel_size
		if(Tracker["constants"]["radius"]  < 1):
			Tracker["constants"]["radius"]  = Tracker["constants"]["nnxo"]//2-2
		elif((2*Tracker["constants"]["radius"] +2) > Tracker["constants"]["nnxo"]):
			ERROR("Particle radius set too large!","sxEKmref_clustering.py",1,myid)

####-----------------------------------------------------------------------------------------
		# Master directory
		if myid == main_node:
			if masterdir =="":
				timestring = strftime("_%d_%b_%Y_%H_%M_%S", localtime())
				masterdir ="master_EKMREF"+timestring
				li =len(masterdir)
				cmd="{} {}".format("mkdir", masterdir)
				cmdexecute(cmd)
			else:
				li = 0
				keepchecking =1			
		else:
			li=0
			keepchecking =1
		li = mpi_bcast(li,1,MPI_INT,main_node,MPI_COMM_WORLD)[0]
		if li>0:
			masterdir = mpi_bcast(masterdir,li,MPI_CHAR,main_node,MPI_COMM_WORLD)
			masterdir = string.join(masterdir,"")
		if myid ==main_node:
			print_dict(Tracker["constants"], "Permanent settings of 3-D sorting program")
		######### create a vstack from input stack to the local stack in masterdir
		# stack name set to default
		Tracker["constants"]["stack"] = "bdb:"+masterdir+"/rdata"
		Tracker["constants"]["ali3d"] = os.path.join(masterdir, "ali3d_init.txt")
		Tracker["constants"]["partstack"] =Tracker["constants"]["ali3d"]
	   	if myid == main_node:
			if keepchecking:
				if(os.path.exists(os.path.join(masterdir,"EMAN2DB/rdata.bdb"))):  doit = False
				else:  doit = True
			else:  doit = True
			if  doit:
				if(orgstack[:4] == "bdb:"):     cmd = "{} {} {}".format("e2bdb.py", orgstack,"--makevstack="+Tracker["constants"]["stack"])
				else:  cmd = "{} {} {}".format("sxcpy.py", orgstack, Tracker["constants"]["stack"])
				cmdexecute(cmd)
				cmd = "{} {}".format("sxheader.py  --consecutive  --params=originalid", Tracker["constants"]["stack"])
				cmdexecute(cmd)
				cmd = "{} {} {} {} ".format("sxheader.py", Tracker["constants"]["stack"],"--params=xform.projection","--export="+Tracker["constants"]["ali3d"])
				cmdexecute(cmd)
				keepchecking = False
			total_stack = EMUtil.get_image_count(Tracker["constants"]["stack"])
		else:
			total_stack = 0
		mpi_barrier(MPI_COMM_WORLD)
		total_stack = bcast_number_to_all(total_stack, source_node = main_node)
		Tracker["total_stack"]= total_stack
		Tracker["constants"]["total_stack"] = total_stack
		Tracker["shrinkage"] = float(Tracker["nxinit"])/Tracker["constants"]["nnxo"] 
		###----------------------------------------------------------------------------------
		# Initial data analysis 
		from random import shuffle
		# Compute the resolution 
		partids =[None]*2
		for procid in xrange(2):partids[procid] =os.path.join(masterdir, "chunk%01d.txt"%procid)
		inivol =[None]*2
		for procid in xrange(2):inivol[procid]  =os.path.join(masterdir,"vol%01d.hdf"%procid)
					
		if myid ==main_node:
			ll=range(total_stack)
			shuffle(ll)
			l1=ll[0:total_stack//2]
			l2=ll[total_stack//2:]
			del ll
			l1.sort()
			l2.sort()
		else:
			l1 = 0
			l2 = 0
		l1 = wrap_mpi_bcast(l1, main_node)
		l2 = wrap_mpi_bcast(l2, main_node)
		### create two volumes to estimate resolution
		Tracker["this_data_list"] = l1
		partids = os.path.join(masterdir,"first_half.txt")
		if myid ==main_node:
			write_text_file(l1,partids)
		mpi_barrier(MPI_COMM_WORLD)
		#print " AAAAAA ",myid, main_node, nproc
		data1,old_shifts1 = get_shrink_data_huang(Tracker,Tracker["nxinit"], partids, Tracker["constants"]["partstack"], myid, main_node, nproc, preshift = True)
		#if myid ==main_node:
		#	print "  XUXU ",Tracker["constants"]["stack"], Tracker["partstack"], myid, nproc
		#data1 =  getindexdata(Tracker["constants"]["stack"], "full.txt", Tracker["partstack"], myid, nproc)
		mpi_barrier(MPI_COMM_WORLD)
		vol1 = recons3d_4nn_ctf_MPI(myid=myid, prjlist = data1, symmetry=Tracker["constants"]["sym"], info=None)
		#vol1,fscxxx = rec3D_MPI(data1, symmetry = Tracker["constants"]["sym"], \
		#	mask3D = None, fsc_curve = None, \
		#	myid = myid, main_node = main_node, odd_start = 1, eve_start = 0, finfo = None, npad = 2, smearstep = 0.0)
		if myid ==main_node:
			vol1_file_name = os.path.join(masterdir, "vol1.hdf")
			vol1.write_image(vol1_file_name)
		mpi_barrier(MPI_COMM_WORLD)
		Tracker["this_data_list"] = l2
		partids = os.path.join(masterdir,"second_half.txt")
		if myid == main_node:
			write_text_file(l2,partids)
		mpi_barrier(MPI_COMM_WORLD)
		data2,old_shifts2 = get_shrink_data_huang(Tracker,Tracker["nxinit"], partids, Tracker["constants"]["partstack"], myid, main_node, nproc, preshift = True)
		vol2 = recons3d_4nn_ctf_MPI(myid=myid, prjlist = data2, symmetry=Tracker["constants"]["sym"], info=None)
		if myid ==main_node:
			vol2_file_name = os.path.join(masterdir, "vol2.hdf")
			vol2.write_image(vol2_file_name)
		mpi_barrier(MPI_COMM_WORLD)
		vols=[vol1,vol2]
		if myid ==main_node:
			low_pass, falloff,currentres =get_resolution_mrk01(vols,Tracker["constants"]["radius"],\
			Tracker["nxinit"],masterdir,None)
			if low_pass >Tracker["constants"]["resolution"]:
				low_pass= Tracker["constants"]["resolution"]
		else:
			low_pass    =0.0
			falloff     =0.0
			currentres  =0.0
		bcast_number_to_all(currentres,source_node = main_node)
		bcast_number_to_all(low_pass,source_node   = main_node)
		bcast_number_to_all(falloff,source_node    = main_node)
		Tracker["currentres"]         = currentres
		Tracker["low_pass"]           = max(low_pass,.25)
		Tracker["falloff"]            = falloff
		Tracker["frequency_low_pass"] =Tracker["constants"]["resolution"]
		if myid ==main_node:
			log_main.add("The command-line inputs are as following:")
			log_main.add("**********************************************************")
		for a in sys.argv:
			if myid ==main_node:
				log_main.add(a)
			else:
				continue
		if myid ==main_node:
			log_main.add("**********************************************************")
		### START 3-D sorting
		if myid ==main_node:
                        log_main.add("----------3-D sorting  program------- ")
			log_main.add("current resolution %6.3f"%Tracker["currentres"])
		mpi_barrier(MPI_COMM_WORLD)
		from utilities import get_input_from_string
		delta       = get_input_from_string(Tracker["constants"]["delta"])
		delta       = delta[0]
		from utilities import even_angles
		n_angles = even_angles(delta, 0, 180)
		this_ali3d  = Tracker["constants"]["ali3d"]
		sampled = get_stat_proj(Tracker,delta,this_ali3d)
		if myid ==main_node:
        		nc = 0
        		for a in sampled:
                		if len(sampled[a])>0:
                        		nc +=1
			log_main.add("total sampled direction %10d  at angle step %6.3f"%(len(n_angles), delta)) 
			log_main.add("captured sampled directions %10d percentage covered by data  %6.3f"%(nc,float(nc)/len(n_angles)*100))
		mpi_barrier(MPI_COMM_WORLD)
		if Tracker["constants"]["number_of_images_per_group"] ==-1: # Estimate number of images per group from delta, and scale up or down by scale_of_number
			number_of_images_per_group = int(Tracker["constants"]["scale_of_number"]*len(n_angles))
			if myid == main_node:
				log_main.add(" Estimate number of images per group from delta and scale up/down by scale_of_number")
				log_main.add(" number_of_images_per_group %d"%number_of_images_per_group)
		else:
			number_of_images_per_group = Tracker["constants"]["number_of_images_per_group"]
			if myid ==main_node:
				log_main.add(" User provided number_of_images_per_group %d"%number_of_images_per_group)
		Tracker["number_of_images_per_group"] = number_of_images_per_group
		number_of_groups = int(total_stack/number_of_images_per_group)
		Tracker["number_of_groups"] =  number_of_groups
		generation     =0
		partition_dict ={}
		full_dict     = {}
		workdir =os.path.join(masterdir,"generation%03d"%generation)
		Tracker["this_dir"] = workdir
		if myid ==main_node:
			log_main.add("---- generation         %5d"%generation)
			log_main.add("number of images per group is set as %d"%number_of_images_per_group)
			log_main.add("the initial number of groups is  %10d "%number_of_groups)
			cmd="{} {}".format("mkdir",workdir)
			cmdexecute(cmd)
		mpi_barrier(MPI_COMM_WORLD)
		create_random_list(Tracker)
		full_dict ={}
		for iptl in xrange(Tracker["constants"]["total_stack"]):
			 full_dict[iptl]=iptl
		Tracker["full_ID_dict"] = full_dict
		#print  Tracker["full_ID_dict"] 	
		for indep_run in xrange(Tracker["constants"]["indep_runs"]):
			Tracker["this_particle_list"] = Tracker["this_indep_list"][indep_run]
			ref_vol= recons_mref(Tracker)
			if myid ==main_node:
				log_main.add("independent run  %10d"%indep_run)
			mpi_barrier(MPI_COMM_WORLD)
			Tracker["this_data_list"]=range(Tracker["constants"]["total_stack"])
			Tracker["total_stack"]   =len(Tracker["this_data_list"])
			Tracker["this_particle_text_file"] = os.path.join(workdir,"independent_list_%03d.txt"%indep_run) # for get_shrink_data
			if myid ==main_node:
				write_text_file(Tracker["this_data_list"],Tracker["this_particle_text_file"])
			mpi_barrier(MPI_COMM_WORLD)
			outdir = os.path.join(workdir, "EQ_Kmeans%03d"%indep_run)
			ref_vol=apply_low_pass_filter(ref_vol,Tracker)
			mref_ali3d_EQ_Kmeans(ref_vol,outdir,Tracker["this_particle_text_file"],Tracker)
			partition_dict[indep_run]=Tracker["this_partition"]
		Tracker["partition_dict"]   = partition_dict
		Tracker["total_stack"]      = len(Tracker["this_data_list"])
		Tracker["this_total_stack"] = Tracker["total_stack"]
		do_two_way_comparison(Tracker)
		ref_vol_list = []
		for igrp in xrange(len(Tracker["two_way_stable_member"])):
			Tracker["this_data_list"]      = Tracker["two_way_stable_member"][igrp]
			Tracker["this_data_list_file"] = os.path.join(workdir,"stable_class%d.txt"%igrp)
			if myid ==main_node:
				write_text_file(Tracker["this_data_list"],Tracker["this_data_list_file"])
			data,old_shifts = get_shrink_data_huang(Tracker,Tracker["nxinit"], Tracker["this_data_list_file"],Tracker["constants"]["partstack"], myid, main_node, nproc, preshift = True)
			volref = recons3d_4nn_ctf_MPI(myid=myid, prjlist = data, symmetry=Tracker["constants"]["sym"], info=None)
			ref_vol_list.append(volref)
			if myid ==main_node:
				log_main.add("group  %d  members %d "%(igrp,len(Tracker["this_data_list"])))	
		ref_vol_list=apply_low_pass_filter(ref_vol_list,Tracker)
		if myid ==main_node:
			for iref in xrange(len(ref_vol_list)):
				ref_vol_list[iref].write_image(os.path.join(workdir,"vol_stable.hdf"),iref)
		mpi_barrier(MPI_COMM_WORLD)
		Tracker["this_data_list"] =Tracker["this_accounted_list"]
		outdir  = os.path.join(workdir,"Kmref")  
		ali3d_mref_Kmeans_MPI(ref_vol_list,outdir,Tracker["this_accounted_text"],Tracker)
		if myid ==main_node:
			log_main.add("number of unaccounted particles  %10d"%len(Tracker["this_unaccounted_list"]))
			log_main.add("number of accounted particles  %10d"%len(Tracker["this_accounted_list"]))
		Tracker["this_data_list"] =Tracker["this_unaccounted_list"]
		Tracker["total_stack"]    =len(Tracker["this_data_list"])
                Tracker["this_total_stack"] = Tracker["total_stack"]
		number_of_groups = int(float(len(Tracker["this_unaccounted_list"]))/number_of_images_per_group)
		Tracker["number_of_groups"] =  number_of_groups
		while number_of_groups >=2:
			generation    +=1
			partition_dict ={}
			workdir =os.path.join(masterdir,"generation%03d"%generation)
			Tracker["this_dir"] = workdir
			if myid ==main_node:
				log_main.add("*********************************************")
				log_main.add("-----    generation             %5d    "%generation)
				log_main.add("number of images per group is set as %10d "%number_of_images_per_group)
				log_main.add("the number of groups is  %10d "%number_of_groups)
				log_main.add(" number of particles for clustering is %10d"%Tracker["total_stack"])
				cmd="{} {}".format("mkdir",workdir)
				cmdexecute(cmd)
			mpi_barrier(MPI_COMM_WORLD)
			create_random_list(Tracker)
			for indep_run in xrange(Tracker["constants"]["indep_runs"]):
				Tracker["this_particle_list"] = Tracker["this_indep_list"][indep_run]
				ref_vol= recons_mref(Tracker)
				if myid ==main_node:
					log_main.add("independent run  %10d"%indep_run)
					outdir = os.path.join(workdir, "EQ_Kmeans%03d"%indep_run)
				Tracker["this_data_list"] =Tracker["this_unaccounted_list"]
				ref_vol=apply_low_pass_filter(ref_vol,Tracker)
				mref_ali3d_EQ_Kmeans(ref_vol,outdir,Tracker["this_unaccounted_text"],Tracker)
				partition_dict[indep_run]=Tracker["this_partition"]
				Tracker["this_data_list"]=Tracker["this_unaccounted_list"]
				Tracker["total_stack"]   =len(Tracker["this_unaccounted_list"])
				Tracker["partition_dict"] =partition_dict
				Tracker["this_total_stack"] = Tracker["total_stack"]
			do_two_way_comparison(Tracker)
			ref_vol_list = []
			for igrp in xrange(len(Tracker["two_way_stable_member"])):
				Tracker["this_data_list"] = Tracker["two_way_stable_member"][igrp]
				Tracker["this_data_list_file"] = os.path.join(workdir,"stable_class%d.txt"%igrp)
				if myid ==main_node:
					write_text_file(Tracker["this_data_list"],Tracker["this_data_list_file"])
				mpi_barrier(MPI_COMM_WORLD)
				data,old_shifts = get_shrink_data_huang(Tracker,Tracker["nxinit"],Tracker["this_data_list_file"],Tracker["constants"]["partstack"],myid,main_node,nproc,preshift = True)
				volref = recons3d_4nn_ctf_MPI(myid=myid, prjlist = data, symmetry=Tracker["constants"]["sym"], info=None)
				ref_vol_list.append(volref)
			ref_vol_list = apply_low_pass_filter(ref_vol_list,Tracker)
			Tracker["this_data_list"] =Tracker["this_accounted_list"]
			outdir       = os.path.join(workdir,"Kmref")
			if myid ==main_node:
				for iref in xrange(len(ref_vol_list)):
					ref_vol_list[iref].write_image(os.path.join(workdir,"vol_stable.hdf"),iref)
			mpi_barrier(MPI_COMM_WORLD)
			ali3d_mref_Kmeans_MPI(ref_vol_list,outdir,Tracker["this_accounted_text"],Tracker)
			if myid ==main_node:
				log_main.add("number of unaccounted particles  %10d"%len(Tracker["this_unaccounted_list"]))
				log_main.add("number of accounted particles  %10d"%len(Tracker["this_accounted_list"]))
			number_of_groups = int(float(len(Tracker["this_unaccounted_list"]))/number_of_images_per_group)
			Tracker["number_of_groups"] =  number_of_groups
			Tracker["this_data_list"]   = Tracker["this_unaccounted_list"]
			Tracker["total_stack"]      = len(Tracker["this_unaccounted_list"])
		# Finish program
		mpi_barrier(MPI_COMM_WORLD)
		from mpi import mpi_finalize
		mpi_finalize()
		exit()
if __name__ == "__main__":
	main()
