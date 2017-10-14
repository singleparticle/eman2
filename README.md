EMAN2 UTILITY
============

Summary
-------
Thise EMAN2 excutable file and scirpt run on BCM cluster.

# Background
## eman2
EMAN2 is the successor to EMAN1. It is a broadly based greyscale scientific image processing suite with a primary focus on processing data from transmission electron microscopes. EMAN's original purpose was performing single particle reconstructions (3-D volumetric models from 2-D cryo-EM images) at the highest possible resolution, but the suite now also offers support for single particle cryo-ET, and tools useful in many other subdisciplines such as helical reconstruction, 2-D crystallography and whole-cell tomography. EMAN2 is capable of processing very large data sets (>100,000 particle) very efficiently.

EMAN2 is now stable and ready for general use. Nonetheless, it is still in its early versions. If you experience any bugs or other problems, please report them to sludtke@bcm.edu. If you find a problem in a release version, you may wish to try the daily snapshot, which represents the most recent development version.

EMAN2 is a scientific image processing suite with a particular focus on single particle reconstruction from cryoEM images. EMAN2 is a complete refactoring of the original EMAN1 library. The new system offers an easily extensible infrastructure, better documentation, easier customization, etc. EMAN2 was designed to happily coexist with EMAN1 installations, for users wanting to experiment, but not ready to completely switch from EMAN1 to EMAN2. 

[Visit EMAN2 Website](http://blake.bcm.edu/emanwiki/EMAN2/)

## About This Package
eman2 run file is about 401MB, and tarball file is about 1.1GB. both of them are too big to upload and management.
The installed bin file are 76MB, lib file are 1.3GB. it's not a good way for adding the bin file and lib file directly into git version control system.

One of the solution is we create a bash or python script in the git repository, the script will be run on user's workstation or cluster.
The script will do following things:
1. Download (with wget) run file or tarball file from archive server(TO BE SETUP);
2. Install or build eman2 binary file in user specified directory;
3. Select latest eman2 version (default) by enviroment modules;
4. Add module file for BCM cluster, and select lastest version (default) by module command;
