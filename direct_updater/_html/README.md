Vendored from CPython v3.11.14 (Lib/html and Lib/_markupbase.py):
https://github.com/python/cpython/tree/v3.11.14/Lib/html

Decky's frozen Python does not bundle html.parser. This private copy includes
its entity table and markup base so release checks and source search do not
depend on the host's optional stdlib modules. Only imports were changed to
relative imports. See LICENSE for the Python license and copyright notices.
