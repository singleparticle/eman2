# eman2

eman2 run file is about 401MB, and tarball file is about 1.1GB. both of them are too big to upload and management.
The installed bin file are 76MB, lib file are 1.3GB. it's not a good way for adding the bin file and lib file directly into git version control system.

One of the solution is we create a bash or python script in the git repository, the script will be run on user's workstation or cluster.
The script will do following things:
1. Download (with wget) run file or tarball file from archive server(TO BE SETUP);
2. Install or build eman2 binary file in user specified directory;
3. Select latest eman2 version (default) by enviroment modules;
4. Add module file for BCM cluster, and select lastest version (default) by module command;
