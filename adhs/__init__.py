import rdflib.plugins.sparql

# To get the best behavior, but still we have https://github.com/RDFLib/rdflib/issues/810
rdflib.plugins.sparql.SPARQL_DEFAULT_GRAPH_UNION = False

# To disable web access: https://github.com/RDFLib/rdflib/issues/810
rdflib.plugins.sparql.SPARQL_LOAD_GRAPHS = False
