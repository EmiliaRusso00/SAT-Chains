import json
import networkx as nx
import minorminer
import sys

# -----------------------------
# CARICAMENTO GRAFI
# -----------------------------
def load_graph_json(path):
    """Carica un grafo da file JSON in networkx"""
    with open(path, "r") as f:
        data = json.load(f)

    G = nx.Graph()
    for n in data["nodes"]:
        if isinstance(n, list) and len(n) == 2 and isinstance(n[1], dict):
            G.add_node(n[0], **n[1])
        else:
            G.add_node(tuple(n) if isinstance(n, list) else n)
    for u, v in data["edges"]:
        u = tuple(u) if isinstance(u, list) else u
        v = tuple(v) if isinstance(v, list) else v
        G.add_edge(u, v)
    return G

def respects_logical_edges(G_logical, embedding, G_physical):
    for u, v in G_logical.edges():
        if u not in embedding or v not in embedding:
            return False
        if not any(G_physical.has_edge(a, b) for a in embedding[u] for b in embedding[v]):
            return False
    return True
# -----------------------------
# FUNZIONE EMBEDDING CON VERIFICA
# -----------------------------
def embed_with_fixed_nodes(G_logical, G_physical, fixed_chains=None, timeout=30):
    """
    Esegue embedding logico -> fisico usando Minorminer
    con controllo della correttezza sugli archi
    """
    fixed_chains = fixed_chains or {}

    print("[INFO] Nodi fissati prima dell'embedding:")
    for n, qset in fixed_chains.items():
        print(f"  Nodo logico {n} -> qubit fisico {sorted(list(qset))}")

    # Usa return_overlap=True per verificare embedding
    embedding, valid = minorminer.find_embedding(
        G_logical.edges(),
        G_physical.edges(),
        fixed_chains=fixed_chains,
        timeout=timeout,
        return_overlap=True
    )

    if embedding:
        print("[INFO] Embedding trovato, validità controllata:")
        print("Embedding valido?" , valid)
        for n in sorted(embedding.keys()):
            print(f"{n} -> {embedding[n]}")
    else:
        print("[FAIL] Nessun embedding trovato.")
    
    if not respects_logical_edges(G_logical, embedding, G_physical):
        print("L'embedding non rispetta gli archi fisici realmente realizzabili")
    return embedding, valid


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso:\n  python simple_embed.py logical.json physical.json")
        sys.exit(1)

    logical_path = sys.argv[1]
    physical_path = sys.argv[2]

    # Carica grafi
    G_log = load_graph_json(logical_path)
    G_phys = load_graph_json(physical_path)

    # Esempio nodi fissati
    fixed_chains = {
        0: {15}, 1: {0}, 2: {2}, 3: {3}, 4: {9}, 5: {6}, 6: {7}, 7: {8}
    }

    embed_with_fixed_nodes(G_log, G_phys, fixed_chains)
