import networkx as nx
import ast
import re
import os
import json

def parse_node(token):
    token = token.strip()

    # tuple
    if token.startswith("(") and token.endswith(")"):
        try:
            return ast.literal_eval(token)
        except:
            raise ValueError(f"Formato nodo tuple non valido: {token}")

    # int
    try:
        return int(token)
    except:
        raise ValueError(f"Nodo non valido: {token}")


def tokenize_line(line):
    """
    Estrae correttamente nodi che possono essere:
    - interi
    - tuple con o senza spazi: (0,0), (0, 0), (1,2,3)
    Restituisce una lista di 1 o 2 token.
    """
    # Regex che cattura:
    # - tuple: \(.*?\)
    # - oppure numeri: \d+
    tokens = re.findall(r"\(.*?\)|\d+", line)

    return tokens


def read_graph(path):
    G = nx.Graph()

    with open(path, 'r') as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith('#'):
                continue

            parts = tokenize_line(line)

            if len(parts) == 1:
                u = parse_node(parts[0])
                G.add_node(u)

            elif len(parts) == 2:
                u = parse_node(parts[0])
                v = parse_node(parts[1])
                G.add_edge(u, v)

            else:
                raise ValueError(f"Linea non riconosciuta (troppi token): {line}")

    return G

def read_graph_json(path):
    if not path or not os.path.isfile(path):
        return None, None  # (grafo, metadata)

    with open(path, "r") as f:
        data = json.load(f)

    G = nx.Graph()

    # Converti nodi hashable
    nodes = []
    for n in data["nodes"]:
        if isinstance(n, list):
            nodes.append(tuple(n))
        else:
            nodes.append(n)
    G.add_nodes_from(nodes)

    # Converti archi hashable
    edges = []
    for u, v in data["edges"]:
        if isinstance(u, list):
            u = tuple(u)
        if isinstance(v, list):
            v = tuple(v)
        edges.append((u, v))

    G.add_edges_from(edges)

    # Metadati del grafo
    metadata = data.get("metadata", {})

    return G, metadata
