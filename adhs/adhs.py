#!/usr/bin/env python
import logging
from flask import Flask, request, render_template, redirect, make_response
from flask.ext.cors import CORS
# from flask_negotiate import consumes, produces
# from adhs_response import *
import rdflib
import argparse
import os
import sys
from werkzeug.http import parse_accept_header, parse_options_header
from rdflib import ConjunctiveGraph
from rdflib.plugins.sparql.parser import parseQuery, parseUpdate
from rdflib.plugins.sparql.algebra import translateQuery, translateUpdate

import rdflib.plugins.sparql
from rdflib.plugins.sparql.algebra import SequencePath

# from Github: https://github.com/RDFLib/rdflib/issues/617
# Egregious hack, the SequencePath object doesn't support compare, this implements the __lt__ method
# so that algebra.py works on sorting in SPARQL queries on e.g. rdf:List paths


def sequencePathCompareLt(self, other):
    return str(self) < str(other)


def sequencePathCompareGt(self, other):
    return str(self) < str(other)


setattr(SequencePath, '__lt__', sequencePathCompareLt)
setattr(SequencePath, '__gt__', sequencePathCompareGt)
# End egregious hack


# To get the best behavior, but still we have https://github.com/RDFLib/rdflib/issues/810
rdflib.plugins.sparql.SPARQL_DEFAULT_GRAPH_UNION = False

# To disable web access: https://github.com/RDFLib/rdflib/issues/810
rdflib.plugins.sparql.SPARQL_LOAD_GRAPHS = False

werkzeugLogger = logging.getLogger('werkzeug')
werkzeugLogger.setLevel(logging.INFO)

logger = logging.getLogger('adhs')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
ch.setFormatter(formatter)


class UnSupportedQuery(Exception):
    """Thrown when providing a query which includes an unsupported keyword."""

    def __init__(self, message=None):
        self.message = message
        pass

    def __str__(self):
        if self.message is not None:
            return ("This query is not supported by this endpoint: {}".format(self.message))
        else:
            return ("This query is not supported by this endpoint")


class UnSupportedQueryType(UnSupportedQuery):
    """Thrown when providing an unsupported query type."""

    pass


# querytype: { accept type: [content type, serializer_format]}
resultSetMimetypes = {
    '*/*': ['application/sparql-results+xml', 'xml'],
    'application/sparql-results+xml': ['application/sparql-results+xml', 'xml'],
    'application/xml': ['application/xml', 'xml'],
    'application/rdf+xml': ['application/rdf+xml', 'xml'],
    'application/json': ['application/json', 'json'],
    'application/sparql-results+json': ['application/sparql-results+json', 'json'],
    'text/csv': ['text/csv', 'csv'],
    'text/html': ['text/html', 'html'],
    'application/xhtml+xml': ['application/xhtml+xml', 'html']
}
rdfMimetypes = {
    '*/*': ['text/turtle', 'turtle'],
    'text/turtle': ['text/turtle', 'turtle'],
    'application/x-turtle': ['application/x-turtle', 'turtle'],
    'application/rdf+xml': ['application/rdf+xml', 'xml'],
    'application/xml': ['application/xml', 'xml'],
    'application/n-triples': ['application/n-triples', 'nt11'],
    'application/trig': ['application/trig', 'trig']
}


def create_result_response(res, mimetype):
    """Create a response with the requested serialization."""
    response = make_response(
        res.serialize(format=mimetype[1]),
        200
    )
    response.headers['Content-Type'] = mimetype[0]
    return response


def negotiate(accept_header):
    """Get the mime type and result format for a Accept Header."""
    formats = {
        'application/rdf+xml': 'xml',
        'text/turtle': 'turtle',
        'application/n-triples': 'nt',
        'application/n-quads': 'nquads'
    }
    best = request.accept_mimetypes.best_match(
        ['application/n-triples', 'application/rdf+xml', 'text/turtle', 'application/n-quads']
    )
    # Return json as default, if no mime type is matching
    if best is None:
        best = 'text/turtle'

    return (best, formats[best])


def parse_query_type(query):
    """Parse a query string into a tuple of querytype and a parsetree.

    Args: query
    Returns: querytype, parsetree
    """
    try:
        translatedQuery = translateQuery(parseQuery(query), {}, None)
        return translatedQuery.algebra.name, translatedQuery
    except Exception:
        pass

    try:
        parsetree = parseUpdate(query)
        translatedUpdate = translateUpdate(parsetree, {}, None)
        return parsetree.request[0].name, translatedUpdate
    except Exception:
        raise UnSupportedQueryType


def parseArgs(args):
    """Parse command line arguments."""
    basepathhelp = "Base path (aka. application root) (WSGI only)."
    loghelp = """Path to the log file."""

    basepath_default = None
    logfile_default = None
    port_default = 5000

    if 'ADHS_BASEPATH' in os.environ:
        basepath_default = os.environ['DHS_BASEPATH']

    if 'ADHS_LOGFILE' in os.environ:
        logfile_default = os.environ['ADHS_LOGFILE']

    if 'ADHS_PORT' in os.environ:
        port_default = os.environ['ADHS_PORT']

    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file')
    parser.add_argument('-b', '--basepath', type=str, default=basepath_default, help=basepathhelp)
    parser.add_argument('--host', default='0.0.0.0', type=str)
    parser.add_argument('-l', '--logfile', type=str, default=logfile_default, help=loghelp)
    parser.add_argument('-p', '--port', default=port_default, type=int)
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-vv', '--verboseverbose', action='store_true')
    parser.add_argument('-i', '--input', default='guess', choices=[
            'html',
            'hturtle',
            'mdata',
            'microdata',
            'n3',
            'nquads',
            'nt',
            'rdfa',
            'rdfa1.0',
            'rdfa1.1',
            'trix',
            'turtle',
            'xml'
        ], help='Optional input format')

    return parser.parse_args(args)

def initialize(args):
    """Build all needed objects.

    Returns:
        A dictionary containing the store object and git repo object.

    """
    if args.verbose:
        ch.setLevel(logging.INFO)
        logger.addHandler(ch)
        logger.debug('Loglevel: INFO')

    if args.verboseverbose:
        ch.setLevel(logging.DEBUG)
        logger.addHandler(ch)
        logger.debug('Loglevel: DEBUG')

    logger.debug("Parsed args: {}".format(args))

    # add the handlers to the logger

    if args.logfile:
        try:
            fh = logging.FileHandler(args.logfile)
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
            logger.debug("Logfile: {}".format(args.logfile))
        except FileNotFoundError:
            logger.error("Logfile not found: {}".format(args.logfile))
            sys.exit('Exiting quit')
        except PermissionError:
            logger.error("Can not create logfile: {}".format(args.logfile))
            sys.exit('Exiting quit')

    # new graph
    g = rdflib.ConjunctiveGraph()

    # parse file into graph
    try:
        with open(args.file, 'r') as fi:
            if args.input == 'guess':
                fo = rdflib.util.guess_format(args.file)
            else:
                fo = args.input
    except Exception:
        logger.info("Can't read file {}".format(args.file))
        sys.exit('Exiting quit')

    try:
        g.parse(args.file, format=fo)
    except Exception:
        logger.info('Can not parse {} as {}.'.format(args.file, fo))
        sys.exit('Exiting quit')

    return g



def create_app(args, store):
    # set up a micro service using flash
    app = Flask(__name__)

    @app.route("/", methods=['GET', 'POST'])
    def index():
        return redirect('/sparql')


    @app.route("/sparql", methods=['POST', 'GET'])
    def sparql():
        """Process a SPARQL query (Select or Update).

        Returns:
            HTTP Response with query result: If query was a valid select query.
            HTTP Response 200: If request contained a valid update query.
            HTTP Response 406: If accept header is not acceptable.
        """
        args = app.config['ARGS']
        g = app.config['STORE']

        query = None
        if request.method == "GET":
            default_graph = request.args.get('default-graph-uri', None)
            named_graph = request.args.get('named-graph-uri', None)
            query = request.args.get('query', None)
        elif request.method == "POST":
            if 'Content-Type' in request.headers:
                contentMimeType, options = parse_options_header(request.headers['Content-Type'])
                if contentMimeType == "application/x-www-form-urlencoded":
                    if 'query' in request.form:
                        default_graph = request.form.get('default-graph-uri', None)
                        named_graph = request.form.get('named-graph-uri', None)
                        query = request.form.get('query', None)
                    elif 'update' in request.form:
                        default_graph = request.form.get('using-graph-uri', None)
                        named_graph = request.form.get('using-named-graph-uri', None)
                        query = request.form.get('update', None)
                elif contentMimeType == "application/sparql-query":
                    default_graph = request.args.get('default-graph-uri', None)
                    named_graph = request.args.get('named-graph-uri', None)
                    query = request.data.decode("utf-8")
                elif contentMimeType == "application/sparql-update":
                    default_graph = request.args.get('using-graph-uri', None)
                    named_graph = request.args.get('using-named-graph-uri', None)
                    query = request.data.decode("utf-8")

        if 'Accept' in request.headers:
            logger.info('Received query via {}: {} with accept header: {}'.format(
                 request.method, query, request.headers['Accept']))
            mimetype = parse_accept_header(request.headers['Accept']).best
        else:
            logger.info('Received query via {}: {} with no accept header.'.format(request.method,
                                                                                  query))
            mimetype = '*/*'

        if query is None:
            if mimetype == 'text/html':
                return render_template('sparql.html', src=args.file, port=request.host)
            else:
                return make_response('No Query was specified or the Content-Type is not set according' +
                                     'to the SPARQL 1.1 standard', 400)

        try:
            queryType, parsedQuery = parse_query_type(query)
        except UnSupportedQueryType as e:
            logger.exception(e)
            return make_response('Unsupported Query Type', 400)

        if queryType in ['InsertData', 'DeleteData', 'Modify', 'DeleteWhere']:
            g.update(parsedQuery)

            try:
                return '', 200
            except Exception as e:
                # query ok, but unsupported query type or other problem during commit
                logger.exception(e)
                return make_response('Error after executing the update query.', 400)

        if queryType in ['SelectQuery', 'DescribeQuery', 'AskQuery', 'ConstructQuery']:
            res = g.query(parsedQuery)

        try:
            if queryType in ['SelectQuery', 'AskQuery']:
                return create_result_response(res, resultSetMimetypes[mimetype])
            elif queryType in ['ConstructQuery', 'DescribeQuery']:
                return create_result_response(res, rdfMimetypes[mimetype])
        except KeyError as e:
            return make_response("Mimetype: {} not acceptable".format(mimetype), 406)

    app.config['STORE'] = store
    app.config['ARGS'] = args
    cors = CORS(app)
    cors.init_app(app)
    return app


def main(args):
    """Start the app."""
    app.run(debug=True, use_reloader=False, host=args.host, port=args.port)
    # app.run(host=args.host,port=args.port)


if __name__ == "__main__":
    parsedArgs = parseArgs(sys.argv[1:])
    g = initialize(parsedArgs)
    sys.setrecursionlimit(2 ** 15)
    app = create_app(args=parsedArgs, store=g)
    main(args=parsedArgs)
