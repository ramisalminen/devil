#  -*- coding: utf-8 -*-
# __init__.py ---
#
# Created: Sat Dec 17 08:38:35 2011 (+0200)
# Author: Janne Kuuskeri
#


import logging, sys
import datamapper
from mappers.xmlmapper import XmlMapper

def init_logging():
    log = logging.getLogger('drest')
    if log.level == logging.NOTSET:
        log.setLevel(logging.WARN)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s %(message)s'))
        log.addHandler(handler)

def register_mappers():
    textmapper = datamapper.DataMapper()
    jsonmapper = datamapper.JsonMapper()
    xmlmapper = XmlMapper(numbermode='basic')

    # text mapper
    datamapper.manager.register_mapper(textmapper, 'text/plain', 'text')

    # xml mapper
    datamapper.manager.register_mapper(xmlmapper, 'text/xml', 'xml')

    # json mapper
    datamapper.manager.register_mapper(jsonmapper, 'application/json', 'json')

    # we'll be tolerant on what we receive
    datamapper.manager.register_mapper(jsonmapper, 'application/x-javascript', 'json')
    datamapper.manager.register_mapper(jsonmapper, 'text/javascript', 'json')
    datamapper.manager.register_mapper(jsonmapper, 'text/x-javascript', 'json')
    datamapper.manager.register_mapper(jsonmapper, 'text/x-json', 'json')

init_logging()
register_mappers()

#
# __init__.py ends here
