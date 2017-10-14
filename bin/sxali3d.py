#!/home/hanxd/arc/EMAN2-bin/EMAN2/extlib/bin/python
#
# Author: Pawel A.Penczek, 09/09/2006 (Pawel.A.Penczek@uth.tmc.edu)
# Copyright (c) 2000-2006 The University of Texas - Houston Medical School
#
# This software is issued under a joint BSD/GNU license. You may use the
# source code in this file under either license. However, note that the
# complete EMAN2 and SPARX software packages have some GPL dependencies,
# so you are responsible for compliance with the licenses of these packages
# if you opt to use BSD licensing. The warranty disclaimer below holds
# in either instance.
#
# This complete copyright notice must be included in any revised version of the
# source code. Additional authorship citations may be added, but existing
# author citations must be preserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307 USA
#
#


import os
import global_def
from global_def import *
from optparse import OptionParser
import sys

def main():

        arglist = []
        for arg in sys.argv:
        	arglist.append( arg )
	progname = os.path.basename(arglist[0])
	usage = progname + " stack ref_vol outdir <maskfile> --ir=inner_radius --ou=outer_radius --rs=ring_step --xr=x_range --yr=y_range  --ts=translational_search_step  --delta=angular_step --an=angular_neighborhood --deltapsi=Delta_psi --startpsi=Start_psi --maxit=max_iter --stoprnct=percentage_to_stop --CTF --snr=SNR  --ref_a=S --sym=c1 --function=user_function --Fourvar=Fourier_variance --debug --MPI"
	parser = OptionParser(usage,version=SPARXVERSION)
	parser.add_option("--ir",       type= "int",         default= 1,                  help="inner radius for rotational correlation > 0 (set to 1)")
	parser.add_option("--ou",       type= "int",         default= -1,                 help="outer radius for rotational correlation < int(nx/2)-1 (set to the radius of the particle)")
	parser.add_option("--rs",       type= "int",         default= 1,                  help="step between rings in rotational correlation >0  (set to 1)" )
	parser.add_option("--xr",       type="string",       default= "4 2 1 1 1",        help="range for translation search in x direction, search is +/xr")
	parser.add_option("--yr",       type="string",       default= "-1",               help="range for translation search in y direction, search is +/yr (default = same as xr)")
	parser.add_option("--ts",       type="string",       default= "1 1 1 0.5 0.25",   help="step size of the translation search in both directions, search is -xr, -xr+ts, 0, xr-ts, xr, can be fractional")
	parser.add_option("--delta",    type="string",       default= "10 6 4 3 2",       help="angular step of reference projections, (default is a sequence: 10 6 4 3 2")
	parser.add_option("--an",       type="string",       default= "-1",               help="angular neighborhood for local searches (phi and theta)")
	parser.add_option("--apsi",     type="string",       default= "-1",               help="angular neighborhood for local searches (psi)")
	parser.add_option("--deltapsi", type="string",       default= "-1",               help="Delta psi for coarse search")
	parser.add_option("--startpsi", type="string",       default= "-1",               help="Start psi for coarse search")
	#parser.add_option("--center",   type="float",        default= -1,                 help="-1: average shift method; 0: no centering; 1: center of gravity (default=-1)")
	parser.add_option("--maxit",    type="float",        default= 5,                  help="maximum number of iterations performed for each angular step (set to 5) ")
	parser.add_option("--stoprnct", type="float",        default=0.0,                 help="Minimum percentage of particles that change orientation to stop the program")
	parser.add_option("--CTF",      action="store_true", default=False,               help="Consider CTF correction during the alignment ")
	parser.add_option("--snr",      type="float",        default= 1.0,                help="Signal-to-Noise Ratio of the data")
	parser.add_option("--ref_a",    type="string",       default= "S",                help="method for generating the quasi-uniformly distributed projection directions (default S)")
	parser.add_option("--sym",      type="string",       default= "c1",               help="symmetry of the refined structure")
	parser.add_option("--function", type="string",       default="ref_ali3d",         help="name of the reference preparation function (ref_ali3d)")
	parser.add_option("--MPI",      action="store_true", default=False,               help="whether to use MPI version")
	parser.add_option("--Fourvar",  action="store_true", default=False,               help="compute Fourier variance")
	parser.add_option("--npad",     type="int",          default= 2,                  help="padding size for 3D reconstruction (default=2)")
	parser.add_option("--debug",    action="store_true", default=False,               help="debug")
	parser.add_option("--shc",      action="store_true", default=False,               help="use SHC algorithm")
	parser.add_option("--nsoft",    type="int",          default= 1,                  help="number of SHC soft assignments (default=1)")
	parser.add_option("--nh2",      action="store_true", default=False,               help="new - SHC2")
	parser.add_option("--ns",       action="store_true", default=False,               help="new - saturn")
	parser.add_option("--ns2",      action="store_true", default=False,               help="new - saturn2")
	parser.add_option("--chunk",    type="float",        default= 0.2,                help="percentage of data used for alignment")
	parser.add_option("--rantest",  action="store_true", default=False,               help="rantest")
	parser.add_option("--searchpsi",action="store_true", default= False,              help="psi refinement")
	parser.add_option("--gamma",    type="float",        default= -1.0,               help="gamma")
	(options, args) = parser.parse_args(arglist[1:])
	if len(args) < 3 or len(args) > 4:
		print "usage: " + usage
		print "Please run '" + progname + " -h' for detailed options"
	else:
		if len(args) == 3 :
			mask = None
		else:
			mask = args[3]
		if options.MPI:
			from mpi import mpi_init, mpi_finalize
			sys.argv = mpi_init(len(sys.argv), sys.argv)

		if global_def.CACHE_DISABLE:
			from utilities import disable_bdb_cache
			disable_bdb_cache()
		#  centering permanently disabled due to the way new polar searches are done
		center = 0
		if(options.ns):
			global_def.BATCH = True
			from development import  ali3d_saturn
			ali3d_saturn(args[0], args[1], args[2], mask, options.ir, options.ou, options.rs, options.xr,
				options.yr, options.ts, options.delta, options.an, options.apsi, options.deltapsi, options.startpsi,
				center, options.maxit, options.CTF, options.snr, options.ref_a, options.sym,
				options.function, options.Fourvar, options.npad, options.debug, options.MPI, options.stoprnct, gamma=options.gamma)
			global_def.BATCH = False
		elif(options.ns2):
			global_def.BATCH = True
			from development import  ali3d_saturn2
			ali3d_saturn2(args[0], args[1], args[2], mask, options.ir, options.ou, options.rs, options.xr,
				options.yr, options.ts, options.delta, options.an, options.apsi, options.deltapsi, options.startpsi,
				center, options.maxit, options.CTF, options.snr, options.ref_a, options.sym,
				options.function, options.Fourvar, options.npad, options.debug, options.MPI, options.stoprnct)
			global_def.BATCH = False
		elif(options.shc):
			if not options.MPI:
				print "Only MPI version is implemented!!!"
			else:
				global_def.BATCH = True
				if(options.nsoft == 1):
					from applications import ali3d_shcMPI
					ali3d_shcMPI(args[0], args[1], args[2], mask, options.ir, options.ou, options.rs, options.xr,
					options.yr, options.ts, options.delta, options.an, options.apsi, options.deltapsi, options.startpsi,
					center, options.maxit, options.CTF, options.snr, options.ref_a, options.sym,
					options.function, options.Fourvar, options.npad, options.debug, options.stoprnct, gamma=options.gamma)
				elif(options.nsoft == 0):
					from applications import ali3d_shc0MPI
					ali3d_shc0MPI(args[0], args[1], args[2], mask, options.ir, options.ou, options.rs, options.xr,
					options.yr, options.ts, options.delta, options.an, options.apsi, options.deltapsi, options.startpsi,
					center, options.maxit, options.CTF, options.snr, options.ref_a, options.sym,
					options.function, options.Fourvar, options.npad, options.debug, options.stoprnct, gamma=options.gamma)
				else:
					from multi_shc import ali3d_multishc_soft
					import user_functions
					options.user_func = user_functions.factory[options.function]
					ali3d_multishc_soft(args[0], args[1], options, mpi_comm = None, log = None, nsoft = options.nsoft )
				global_def.BATCH = False
		elif(options.nh2):
			global_def.BATCH = True
			from development import ali3d_shc2
			ali3d_shc2(args[0], args[1], args[2], mask, options.ir, options.ou, options.rs, options.xr,
				options.yr, options.ts, options.delta, options.an, options.apsi, options.deltapsi, options.startpsi,
				center, options.maxit, options.CTF, options.snr, options.ref_a, options.sym,
				options.function, options.Fourvar, options.npad, options.debug, options.MPI, options.stoprnct)
			global_def.BATCH = False
		elif options.searchpsi:
			from applications import ali3dpsi_MPI
			global_def.BATCH = True
			ali3dpsi_MPI(args[0], args[1], args[2], mask, options.ir, options.ou, options.rs, options.xr,
			options.yr, options.ts, options.delta, options.an, options.apsi, options.deltapsi, options.startpsi,
			center, options.maxit, options.CTF, options.snr, options.ref_a, options.sym,
			options.function, options.Fourvar, options.npad, options.debug, options.stoprnct)
			global_def.BATCH = False
		else:
			if options.rantest:
				from development import ali3d_rantest
				global_def.BATCH = True
				ali3d_rantest(args[0], args[1], args[2], mask, options.ir, options.ou, options.rs, options.xr,
				options.yr, options.ts, options.delta, options.an, options.deltapsi, options.startpsi,
				center, options.maxit, options.CTF, options.snr, options.ref_a, options.sym,
				options.function, options.Fourvar, options.npad, options.debug, options.stoprnct)
				global_def.BATCH = False
			else:
				from applications import ali3d
				global_def.BATCH = True
				ali3d(args[0], args[1], args[2], mask, options.ir, options.ou, options.rs, options.xr,
				options.yr, options.ts, options.delta, options.an, options.apsi, options.deltapsi, options.startpsi,
				center, options.maxit, options.CTF, options.snr, options.ref_a, options.sym,
				options.function, options.Fourvar, options.npad, options.debug, options.MPI, options.stoprnct)
				global_def.BATCH = False

		if options.MPI:  mpi_finalize()

if __name__ == "__main__":
	main()
