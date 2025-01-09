# jdav Kompass

[![Build Status](https://jenkins.merten.dev/buildStatus/icon?job=gitea%2Fkompass%2Fmain)](https://jenkins.merten.dev/job/gitea/job/kompass/job/main/)

Kompass is an administration platform designed for local sections of the Young German Alpine Club. It provides
tools to contact and (automatically) manage members, groups, material, excursions and statements.

For more details on the features, see the (German) [documentation](https://jdav-hd.de/static/docs/index.html).

# Contributing

Any form of contribution is appreciated. If you found a bug or have a feature request, please file an
[issue](https://git.jdav-hd.merten.dev/digitales/kompass/issues). If you want to help with the documentation or
want to contribute code, please open a [pull request](https://git.jdav-hd.merten.dev/digitales/kompass/pulls).

The following is a short description of where to find the documentation with more information.


# Documentation 

Documentation is handled by [sphinx](https://www.sphinx-doc.org/) and located in `docs/`. 

The sphinx documentation contains information about:
- Development Setup
- Architecture
- Testing
- Production Deployment
- End user documentation
- and much more...

> Please add all further documentation also in the sphinx documentation. And not in the readme

## online
Online (latest release version): https://jdav-hd.de/static/docs/

## local
To read the documentation build it locally and view it in your browser:
```bash
cd docs/
make html

# MacOS (with firefox)
open -a firefox $(pwd)/docs/build/html/index.html 
# Linux (I guess?!?)
firefox ${pwd}/docs/build/html/index.html 
```
