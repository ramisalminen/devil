#  -*- coding: utf-8 -*-
# datamapper.py ---
#
# Created: Thu Dec 15 10:03:04 2011 (+0200)
# Author: Janne Kuuskeri
#


import re, types
import xml.sax.handler
import simplejson as json
from decimal import Decimal, InvalidOperation
from django.utils.encoding import smart_unicode, smart_str
from django.http import HttpResponse
from django.utils.xmlutils import SimplerXMLGenerator
import errors
from http import Response
import util


try:
    import cStringIO as StringIO
except ImportError:
    import StringIO


class DataMapper(object):
    """ Base class for all data mappers.


    """

    content_type = 'text/plain'
    charset = 'utf-8'

    def format(self, response):
        """ Format the data.

        It is usually a better idea to override `_format_data()` than
        this method in derived classes.

        @param response drests's `Response` object or the data
        itself. May also be `None`.
        """

        res = self._prepare_response(response)
        res.content = self._format_data(res.content, self.charset)
        return self._finalize_response(res)

    def parse(self, data, charset=None):
        """ Parse the data.

        It is usually a better idea to override `_parse_data()` than
        this method in derived classes.

        @param charset the charset of the data. Uses datamapper's
        default (`self.charset`) if not given.
        """

        charset = charset or self.charset
        return self._parse_data(data, charset)

    def _decode_data(self, data, charset):
        """ Decode string data.

        @return unicode string
        """

        try:
            return smart_unicode(data, charset)
        except UnicodeDecodeError:
            raise errors.BadRequest('wrong charset')

    def _encode_data(self, data):
        """ Encode string data. """
        return smart_str(data, self.charset)

    def _format_data(self, data, charset):
        """ Format the data

        @param data the data (may be None)
        """

        return self._encode_data(data) if data else u''

    def _parse_data(self, data, charset):
        """ Parse the data

        @param data the data (may be None)
        """

        return self._decode_data(data, charset) if data else u''

    def _prepare_response(self, response):
        """ Coerce response to drest's Response

        @param response either the response data or a `Response` object.
        @return Response object
        """

        if not isinstance(response, Response):
            return Response(0, response)
        return response

    def _finalize_response(self, response):
        """ Convert the `Response` object into django's `HttpResponse` """

        res = HttpResponse(content=response.content,
                           content_type=self._get_content_type())
        # status_code is set separately to allow zero
        res.status_code = response.code
        return res

    def _get_content_type(self):
        """ Return Content-Type header with charset info. """
        return '%s; charset=%s' % (self.content_type, self.charset)


class JsonMapper(DataMapper):
    content_type = 'application/json'

    def _format_data(self, data, charset):
        if data is None or data == '':
            return u''
        else:
            return json.dumps(
                data, indent=4, ensure_ascii=False, encoding=charset)

    def _parse_data(self, data, charset):
        try:
            return json.loads(data, charset)
        except ValueError:
            raise errors.BadRequest('unable to parse data')


class JsonDecimalMapper(DataMapper):
    """ Json mapper that uses Decimals instead of floats """

    content_type = 'application/json'

    def _format_data(self, data, charset):
        if data is None or data == '':
            return u''
        else:
            return json.dumps(
                data, indent=4, ensure_ascii=False, encoding=charset, use_decimal=True)

    def _parse_data(self, data, charset):
        try:
            return json.loads(data, charset, use_decimal=True)
        except ValueError:
            raise errors.BadRequest('unable to parse data')


class XmlMapper(DataMapper):

    content_type = 'text/xml'

    def _parse_data(self, data, charset):
        return xml2obj(data)['root']

    def _format_data(self, data, charset):
        if data is None or data == '':
            return u''

        stream = StringIO.StringIO()
        xml = SimplerXMLGenerator(stream, charset)
        xml.startDocument()
        xml.startElement(self._root_element_name(), {})
        self._to_xml(xml, data)
        xml.endElement(self._root_element_name())
        xml.endDocument()
        return stream.getvalue()

    def _to_xml(self, xml, data, key=None):
        if isinstance(data, (list, tuple)):
            for item in data:
                elemname = self._list_item_element_name(key)
                xml.startElement(elemname, {})
                self._to_xml(xml, item)
                xml.endElement(elemname)
        elif isinstance(data, dict):
            for key, value in data.iteritems():
                xml.startElement(key, {})
                self._to_xml(xml, value, key)
                xml.endElement(key)
        else:
            xml.characters(smart_unicode(data))

    def _root_element_name(self):
        return 'root'

    def _list_item_element_name(self, key=None):
        key = key or ''
        return '%s_item' % (key,)


class DataMapperManager(object):
    """ DataMapperManager tries to parse and format payload data when
    possible.

    First, try to figure out the content-type of the data, then find
    corresponding mapper and parse/format the data. If no mapper is
    registered or the content-type can't be determined, does nothing.

    Following order is used when determining the content-type.
    1. Content-Type HTTP header (for parsing only)
    2. "format" query parameter (e.g. ?format=json)
    3. file-extension in the requestd URL (e.g. /user.json)
    """

    _default_mapper = DataMapper()
    _format_query_pattern = re.compile('.*\.(?P<format>\w{1,8})$')
    _datamappers = {
        }

    def register_mapper(self, mapper, content_type, shortname=None):
        """ Register new mapper.

        @param mapper mapper object needs to implement `parse()` and
        `format()` functions.
        """

        self._check_mapper(mapper)
        self._datamappers[content_type] = mapper
        if shortname:
            self._datamappers[shortname] = mapper

    def select_formatter(self, request, default_formatter=None):
        mapper_name = self._get_short_name(request)
        if not mapper_name:
            mapper_name = self._parse_access_header(request)
        return self._get_mapper(mapper_name, default_formatter)

    def select_parser(self, request, default_parser=None):
        mapper_name = self._get_mapper_name(request)
        return self._get_mapper(mapper_name, default_parser)

    def get_mapper_by_content_type(self, content_type):
        content_type = util.strip_charset(content_type)
        return self._get_mapper(content_type)

    def set_default_mapper(self, mapper):
        """ Set the default mapper to be used, when no format is defined.

        If given mapper is None, uses the `DataMapper`.
        """

        if mapper is None:
            self._default_mapper = DataMapper()
        else:
            self._check_mapper(mapper)
            self._default_mapper = mapper

    def _get_mapper(self, mapper_name, default_mapper=None):
        """ Select appropriate mapper for the incoming data. """
        if not mapper_name:
            # unspecified -> use default
            return self._get_default_mapper(default_mapper)
        elif not mapper_name in self._datamappers:
            # unknown
            return self._unknown_format(mapper_name)
        else:
            # mapper found
            return self._datamappers[mapper_name]

    def _get_mapper_name(self, request):
        """ """
        content_type = request.META.get('CONTENT_TYPE', None)

        if not content_type:
            return self._get_short_name(request)
        else:
            # remove the possible charset-encoding info
            return util.strip_charset(content_type)

    def _parse_access_header(self, request):
        """ Parse the Access HTTP header.

        :returns: the
        """

        accepts = util.parse_accept_header(request.META.get("HTTP_ACCEPT", ""))
        for accept in accepts:
            if accept[0] in self._datamappers:
                return accept[0]
        return None

    def _get_short_name(self, request):
        """ Determine short name for the mapper.

        Short name can be either in query string (e.g. ?format=json)
        or as an extension to the URL (e.g. myresource.json).

        :returns: short name of the mapper or `None` if not found.
        """

        format = request.GET.get('format', None)
        if not format:
            match = self._format_query_pattern.match(request.path)
            if match and match.group('format'):
                format = match.group('format')
        return format

    def _get_default_mapper(self, resource_default_mapper):
        """ Return default mapper for the resource.

        todo: optimize. isinstance gets called on every request if
        mapper isn't specified explicitly.
        """

        # if resource didn't give any default mapper, use our default mapper
        if not resource_default_mapper:
            return self._default_mapper

        # resource did define a default mapper (either string or mapper obj)
        if isinstance(resource_default_mapper, basestring):
            return self._get_mapper(resource_default_mapper)
        else:
            return resource_default_mapper

    def _unknown_format(self, format):
        """ """
        raise errors.NotAcceptable('unknown data format: ' + format)

    def _check_mapper(self, mapper):
        """ Check that the mapper has valid signature. """
        if not hasattr(mapper, 'parse') or not callable(mapper.parse):
            raise ValueError('mapper must implement parse()')
        if not hasattr(mapper, 'format') or not callable(mapper.format):
            raise ValueError('mapper must implement format()')


# singleton instance
manager = DataMapperManager()

# utility function to format outgoing data (selects formatter automatically)
def format(request, response, default_mapper=None):
    return manager.select_formatter(request, default_mapper).format(response)

# utility function to parse incoming data (selects parser automatically)
def parse(data, request, default_mapper=None):
    charset = util.get_charset(request)
    return manager.select_parser(request, default_mapper).parse(data, charset)


#
# datamapper.py ends here


def xml2obj(src):
    """
    A simple function to converts XML data into native Python object.
    """

    def element_to_py(node, name, value):
        """ Convert a single element (from xml tree) into value.


        """

        try:
            node.append(value)
        except AttributeError:
            pass
        else:
            return node

        if name in node:
            node = node.values() + [value]
        else:
            node[name] = value
        return node

    class TreeBuilder(xml.sax.handler.ContentHandler):
        def __init__(self):
            self.stack = []
            self.root = {}
            self.current = self.root
            self.text_parts = []
        def startElement(self, name, attrs):
            self.stack.append((self.current, self.text_parts))
            self.current = {}
            self.text_parts = []
        def endElement(self, name):
            if self.current:
                obj = self.current
            else:
                # text only node is simply represented by the string or Decimal
                text = ''.join(self.text_parts).strip()
                try:
                    obj = Decimal(text)
                except InvalidOperation:
                    obj = text or ''
            self.current, self.text_parts = self.stack.pop()
            self.current = element_to_py(self.current, name, obj)
        def characters(self, content):
            self.text_parts.append(content)

    builder = TreeBuilder()
    if isinstance(src,basestring):
        xml.sax.parseString(src, builder)
    else:
        xml.sax.parse(src, builder)
    return builder.root
