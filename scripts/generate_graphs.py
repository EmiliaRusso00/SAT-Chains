import networkx as nx
import os
import json
import random
from itertools import product

try:
    import dwave_networkx as dnx
    DWAVE_AVAILABLE = True
except ImportError:
    DWAVE_AVAILABLE = False

# ---------------------------------------------------------
# SALVATORE FILE TXT
# ---------------------------------------------------------
def save_graph_txt(G, path):
    with open(path, 'w') as f:
        for u, v in G.edges():
            f.write(f"{u} {v}\n")
        for u in nx.isolates(G):
            f.write(f"{u}\n")
    print(f"[ OK ] Grafo salvato in {path}")


# ---------------------------------------------------------
# SALVATORE FILE JSON (VERSIONE CORRETTA)
# ---------------------------------------------------------
def save_graph_json(G, path, metadata):
    """
    Salva un grafo NetworkX (anche D-Wave) in JSON compatto con:
    - nodes : lista di nodi o di (nodo, attributi)
    - edges : lista di [u, v, attributi]
    - metadata : dict fornito
    - graph_attributes : attributi globali del grafo G.graph
    Ogni campo è stampato su una riga separata.
    """
    # Estrai nodi con attributi
    nodes_list = []
    for n, attrs in G.nodes(data=True):
        if attrs:
            nodes_list.append([n, attrs])
        else:
            nodes_list.append(n)

    # Estrai archi con attributi
    edges_list = []
    for u, v, attrs in G.edges(data=True):
        if attrs:
            edges_list.append([u, v, attrs])
        else:
            edges_list.append([u, v])

    # Dizionario JSON finale
    data = {
        "nodes": nodes_list,
        "edges": edges_list,
        "metadata": metadata,
        "graph_attributes": dict(G.graph)  # <--- qui aggiunto
    }

    # Scrittura compatta e con campi separati
    with open(path, "w") as f:
        f.write("{\n")
        f.write(f'  "nodes":{json.dumps(data["nodes"], separators=(",", ":"))},\n')
        f.write(f'  "edges":{json.dumps(data["edges"], separators=(",", ":"))},\n')
        f.write(f'  "metadata":{json.dumps(data["metadata"], separators=(",", ":"))},\n')
        f.write(f'  "graph_attributes":{json.dumps(data["graph_attributes"], separators=(",", ":"))}\n')
        f.write("}\n")

    print(f"[ OK ] Grafo JSON salvato in {path}")




# ---------------------------------------------------------
# CARICATORE FILE JSON (NUOVA FUNZIONE)
# ---------------------------------------------------------
def load_graph_json(path):
    with open(path, 'r') as f:
        data = json.load(f)

    G = nx.Graph()
    G.add_nodes_from(data["nodes"])
    G.add_edges_from(data["edges"])

    # Ripristino attributi interni D-Wave
    if "graph_attributes" in data:
        G.graph.update(data["graph_attributes"])

    metadata = data.get("metadata", {})
    return G, metadata


# ---------------------------------------------------------
# GENERATORI STANDARD
# ---------------------------------------------------------
def gen_random_graph(n, p=0.3):
    return nx.erdos_renyi_graph(n, p)

def gen_tree(n):
    return nx.random_labeled_tree(n)

def gen_grid_2d(m, n):
    return nx.grid_2d_graph(m, n)

def gen_grid_3d(m, n, p):
    return nx.grid_graph(dim=[m, n, p])

def gen_clique(n):
    return nx.complete_graph(n)

def gen_bipartite(a, b):
    return nx.complete_bipartite_graph(a, b)

def gen_star(n):
    return nx.star_graph(n)

def gen_cycle(n):
    return nx.cycle_graph(n)

def gen_line(n):
    return nx.path_graph(n)

def gen_small_world(n, k, p):
    return nx.watts_strogatz_graph(n, k, p)

def gen_scale_free(n):
    return nx.barabasi_albert_graph(n, m=2)

def gen_fan(n):
    """
    Crea un fan graph con n raggi (n >= 2)
    Un fan graph è un path di n nodi più un nodo centrale collegato a tutti i nodi del path
    """
    if n < 2:
        raise ValueError("Fan graph must have at least 2 nodes")
    
    G = nx.path_graph(n)          # path di n nodi
    center = n                    # nodo centrale
    G.add_node(center)
    for i in range(n):
        G.add_edge(center, i)
    return G

def gen_wheel(n):
    return nx.wheel_graph(n)

# ---------------------------------------------------------
# GENERATORI D-WAVE
# ---------------------------------------------------------
def require_dwave():
    if not DWAVE_AVAILABLE:
        raise RuntimeError("dwave_networkx NON è installato. Installa con: pip install dwave-networkx")

def gen_chimera(M, N, L):
    require_dwave()
    return dnx.chimera_graph(M, N, L)

def gen_pegasus(m):
    require_dwave()
    return dnx.pegasus_graph(m)

def gen_zephyr(m, t):
    require_dwave()
    return dnx.zephyr_graph(m, t)


# ---------------------------------------------------------
# MENU E GENERAZIONE
# ---------------------------------------------------------
def main():

    print("\n=== GENERATORE DI GRAFI ===")
    
    types = {
        "1": "random",
        "2": "tree",
        "3": "grid2d",
        "4": "grid3d",
        "5": "clique",
        "6": "bipartite",
        "7": "star",
        "8": "cycle",
        "9": "line",
        "10": "smallworld",
        "11": "scalefree",
        "12": "fan",
        "13": "wheel",
        "14": "chimera",
        "15": "pegasus",
        "16": "zephyr"
    }

    for k, v in types.items():
        print(f"{k}) {v}")

    choice = input("\nScegli un tipo di grafo: ")

    metadata = {}
    G = None

    # -----------------------------------------------------
    if choice == "1":
        n = int(input("Numero nodi: "))
        p = float(input("Probabilità arco (0-1): "))
        G = gen_random_graph(n, p)
        metadata = {"type": "random", "n": n, "p": p}

    elif choice == "2":
        n = int(input("Numero nodi: "))
        G = gen_tree(n)
        metadata = {"type": "tree", "n": n}

    elif choice == "3":
        m = int(input("Righe: "))
        n = int(input("Colonne: "))
        G = gen_grid_2d(m, n)
        metadata = {"type": "grid2d", "rows": m, "cols": n}

    elif choice == "4":
        x = int(input("Dimensione X: "))
        y = int(input("Dimensione Y: "))
        z = int(input("Dimensione Z: "))
        G = gen_grid_3d(x, y, z)
        metadata = {"type": "grid3d", "dim": [x, y, z]}

    elif choice == "5":
        n = int(input("Numero nodi: "))
        G = gen_clique(n)
        metadata = {"type": "clique", "n": n}

    elif choice == "6":
        a = int(input("Lato A: "))
        b = int(input("Lato B: "))
        G = gen_bipartite(a, b)
        metadata = {"type": "bipartite", "a": a, "b": b}

    elif choice == "7":
        n = int(input("Numero foglie: "))
        G = gen_star(n)
        metadata = {"type": "star", "n": n}

    elif choice == "8":
        n = int(input("Numero nodi: "))
        G = gen_cycle(n)
        metadata = {"type": "cycle", "n": n}

    elif choice == "9":
        n = int(input("Numero nodi: "))
        G = gen_line(n)
        metadata = {"type": "line", "n": n}

    elif choice == "10":
        n = int(input("Numero nodi: "))
        k = int(input("Numero vicini: "))
        p = float(input("Probabilità ri-wire (0-1): "))
        G = gen_small_world(n, k, p)
        metadata = {"type": "smallworld", "n": n, "k": k, "p": p}

    elif choice == "11":
        n = int(input("Numero nodi: "))
        G = gen_scale_free(n)
        metadata = {"type": "scalefree", "n": n}

    elif choice == "12":
        n = int(input("Numero nodi: "))
        G = gen_fan(n)
        metadata = {"type": "fan", "n": n}
    
    elif choice == "13":
        n = int(input("Numero nodi: "))
        G = gen_wheel(n)
        metadata = {"type": "wheel", "n": n}

    elif choice == "14":
        M = int(input("M (righe celle): "))
        N = int(input("N (colonne celle): "))
        L = int(input("L (dimensione bipartizione, tipicamente 4): "))
        G = gen_chimera(M, N, L)
        metadata = {"type": "chimera", "rows": M, "cols": N, "tile": L, "original_dwave_graph": True}

    elif choice == "15":
        m = int(input("Dimensione m (es. 2..16): "))
        G = gen_pegasus(m)
        metadata = {"type": "pegasus", "m": m,"original_dwave_graph": True}

    elif choice == "16":
        m = int(input("Dimensione m (es. 3..20): "))
        t = int(input("Dimensione bipartizione t (tipicamente 4): "))
        G = gen_zephyr(m, t)
        metadata = {"type": "zephyr", "m": m, "t": t,"original_dwave_graph": True}

    else:
        print("Scelta non valida.")
        return

    # -----------------------------------------------------
    # SALVATAGGIO
    # -----------------------------------------------------
    os.makedirs("graphs", exist_ok=True)
    filename = input("\nNome file output (senza estensione): ")
    
    txt_path = f"graphs/{filename}.txt"
    json_path = f"graphs/{filename}.json"

    save_graph_txt(G, txt_path)
    save_graph_json(G, json_path, metadata)

    print("\nFatto!")

if __name__ == "__main__":
    main()
