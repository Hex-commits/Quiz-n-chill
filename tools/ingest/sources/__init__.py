"""Where articles come from.

One implementation today, Wikipedia, but it is a layer rather than a module
because the rest of the tool only needs `Article` -- a title, a URL and some
text. Anything that can produce those could feed the same pipeline.

Imports nothing else from the package: it is the outermost edge on the way in.
"""
