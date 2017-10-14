#!/home/hanxd/arc/EMAN2-bin/EMAN2/extlib/bin/python

#
# Authors: James Michael Bell, 06/03/2015
# Copyright (c) 2015 Baylor College of Medicine
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
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA	2111-1307 USA
#

from __future__ import print_function
from EMAN2 import *
import sys

def main():
	progname = os.path.basename(sys.argv[0])
	usage = """prog [options] <image1> <image2>....
	
	Creates a stack of images for each input file. The stack consists of a moving 
	window across each file of a specified size and step. An example use case for 
	this program is to create test data for particle filtering, centering and 
	general image processing.
	"""
	parser = EMArgumentParser(usage=usage,version=EMANVERSION)
	
	parser.add_argument("--boxsize",type=int,help="Box size for each tile in pixels. Default is 512.",default=512)
	parser.add_argument("--xmin",type=int,help="Start tiling on this x-pixel. If -1, will start one boxsize inward.",default=-1)
	parser.add_argument("--xmax",type=int,help="Generate tiles in x-direction until this many pixels. If -1, will tile the entire image.",default=-1)
	parser.add_argument("--xstep",type=int,help="Step length in x-direction. If less than --boxsize, tiles will overlap. Default is 256.",default=256)
	parser.add_argument("--ymin",type=int,help="Start tiling on this y-pixel. If -1, will start one boxsize inward.",default=-1)
	parser.add_argument("--ymax",type=int,help="Generate tiles in y-direction until this many pixels. If -1, will tile the entire image.",default=-1)
	parser.add_argument("--ystep",type=int,help="Step length in y-direction. If less than --boxsize, tiles will overlap. Default is 256.",default=256)
	parser.add_argument("--verbose", "-v", dest="verbose", action="store", metavar="n", type=int, default=0, help="verbose level [0-9], higner number means higher level of verboseness")
	
	(options, args) = parser.parse_args()
	
	if options.xmin < -1 or options.ymin < -1:
		print("--xmin and --ymin must be greater than or equal to -1.")
		sys.exit(1)
	
	if options.xmin == -1: options.xmin = options.boxsize
	if options.ymin == -1: options.xmin = options.boxsize
	
	for i,fname in enumerate(args):
		if options.verbose > 2: print("Processing {}".format(fname))
		outfile = os.path.relpath(fname).split('.')[-2] + '_tiles.hdf'
		
		hdr = EMData(fname,0,True)
		if options.xmax > hdr['nx']-options.boxsize:
			print("--xmax is too large for file")
			continue
		if options.ymax > hdr['ny']-options.boxsize:
			print("--ymax is too large for file")
			continue
		
		if options.xmax == -1: options.xmax = hdr['nx'] - options.boxsize
		if options.ymax == -1: options.ymax = hdr['ny'] - options.boxsize
		
		t = 0
		ys = xrange(options.ymin,options.ymax,options.ystep)
		xs = xrange(options.xmin,options.xmax,options.xstep)
		nt = len(ys)*len(xs)
		for y in ys:
			for x in xs:
				tile = EMData(fname,0,False,Region(x,y,options.boxsize,options.boxsize))
				if options.verbose > 6:
					print("tile {}/{}".format(t+1,nt),end="\r")
					sys.stdout.flush()
				tile.write_image(outfile,t)
				t += 1

if __name__ == "__main__":
	main()
