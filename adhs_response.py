from flask import Response, render_template, Markup
from rdflib.plugins import sparql

def get_response(qres, output):
    if qres == None:
        return Response("ignored", content_type=output)
    if output == 'application/sparql-results+json':
        return Response(
                qres.serialize(format='json').decode('utf-8'),
                content_type='application/sparql-results+json'
                )
    elif output == 'text/html':
        return render_template('response.html', tabledata=Markup(html_serialize(qres)))
    elif output == 'application/sparql-results+xml':
        return Response(
                qres.serialize(format='xml').decode('utf-8'),
                content_type='application/sparql-results+xml')
    elif output == 'application/rdf+xml':
        return Response(
                qres.serialize(format='xml').decode('utf-8'),
                content_type='application/rdf+xml')

    else:
        return None

def execute_query(query, g):
    try:
        parsedQuery = sparql.processor.prepareQuery(query)
        if str(parsedQuery.algebra.name) in ['ConstructQuery', 'SelectQuery', 'AskQuery']:
            return g.query(parsedQuery)
        else:
            # Other types, e.g. DESCRIBE have to be ignored. DESCRIBE is not supported by RDFlib
            return None
    except:
        print "update"
        parsedQuery = sparql.processor.prepareUpdate(query)
        g.update(parsedQuery)
        return None

def html_serialize(result):
    '''
    Outputs the result of a rdflib.query
    '''

    output = '    <tr>\n'
    for v in result.vars:
        output += '        <th>%s</th>\n' % v
    output += '    </tr>\n'

    for row in result:
        output += '    <tr>\n'
        for val in row:
            output += '        <td>%s</td>\n' % (val if (val != None) else '')
        output += '    </tr>'
    return output
