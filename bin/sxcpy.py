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
from applications  import  cpy

import global_def
from global_def import *

from optparse import OptionParser
import sys

def main():
	progname = os.path.basename(sys.argv[0])
	usage = progname + " stack_in  stack_out"
	parser = OptionParser(usage,version=SPARXVERSION)
	(options, args) = parser.parse_args()

	if global_def.CACHE_DISABLE:
		from utilities import disable_bdb_cache
		disable_bdb_cache()
	
	# check length of arguments list. less than 2 is illegal
	if (len(args) < 2):
    		print "usage: " + usage
    		print "Please run '" + progname + " -h' for detailed options"
	# 2 is file to file copying
	elif (2 == len(args)):
		#print "file to file"
		cpy(args[0], args[1])
	# more than 2, this means a wildcard is transformed to a list of filenams
	else:
		#print "list to file"
		#
		# XXX: note that wildcards only work for filenames! wildcards in files
		#    are processed by the shell and read in as a space-delimited list
		#    of filenames. however, this does NOT work for bdb:image1 type names,
		#    since these will not be found and processed by the shell, not being
		#    normal files. globbing of db objects will have to be done here!
		#
		# make sure we only pass the last entry of args as output file name,
		#    since [-1:] pass a list containing only the last entry....
		#
		# application.cpy
		cpy(args[:-1], args[-1:][0])
		
if __name__ == "__main__":
	main()
