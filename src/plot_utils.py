import os
import matplotlib.pyplot as plt
import networkx as nx
from utils import ensure_dir
from itertools import combinations

try:
    import dwave_networkx as dnx
    from dwave_networkx import draw_chimera, draw_pegasus, draw_zephyr, chimera_graph, pegasus_graph, zephyr_graph
    DWAVE_AVAILABLE = True
except ImportError:
    DWAVE_AVAILABLE = False

def normalize_node(n):
    if isinstance(n, tuple):
        return n
    if isinstance(n, list):
        return tuple(n)
    return (n,)

def plot_embedding_results(G_logical, solution_json, save_dir, exp_id,
                           physical_metadata=None, show_labels=True):

    ensure_dir(save_dir)

    # --- Ricostruisce solution_map ---
    solution_map = {}
    if solution_json and "solutions" in solution_json and solution_json["solutions"]:
        assignment = solution_json["solutions"][0].get("assignment", {})
        for k, v in assignment.items():
            solution_map[int(k)] = v if isinstance(v, list) else [v]

    # --- Grafo fisico D-Wave ---
    gtype = physical_metadata.get("type", "").lower()
    if gtype == "chimera":
        G_phys = chimera_graph(physical_metadata["rows"], physical_metadata["cols"], physical_metadata["tile"])
        pos_phys = dnx.chimera_layout(G_phys)
    elif gtype == "pegasus":
        G_phys = pegasus_graph(physical_metadata["m"])
        pos_phys = dnx.pegasus_layout(G_phys)
    elif gtype == "zephyr":
        G_phys = zephyr_graph(physical_metadata["m"], physical_metadata.get("t", 1))
        pos_phys = dnx.zephyr_layout(G_phys)
    else:
        raise ValueError(f"Unknown physical graph type: {gtype}")

    # ---------------------------
    # 1️ Grafo logico
    # ---------------------------
    plt.figure(figsize=(6,6))
    nx.draw(G_logical, with_labels=show_labels, node_color='skyblue', node_size=200)
    plt.title(f"Logical Graph – Experiment {exp_id}")
    plt.tight_layout()
    path_log = os.path.join(save_dir, f"exp_{exp_id}_logical.png")
    plt.savefig(path_log, dpi=400)
    plt.close()
    print(f"[INFO] Logical graph saved: {path_log}")

    # ---------------------------
    # 2️ Grafo fisico D-Wave
    # ---------------------------
    plt.figure(figsize=(8,8))
    if gtype == "chimera":
        draw_chimera(G_phys, node_size=40, node_color='lightgray', edge_color='black')
    elif gtype == "pegasus":
        draw_pegasus(G_phys, crosses=True, node_size=40, node_color='lightgray', edge_color='black')
    elif gtype == "zephyr":
        draw_zephyr(G_phys, node_size=50, node_color='lightgray', edge_color='black')
    plt.title(f"Physical Graph – Experiment {exp_id}")
    plt.tight_layout()
    path_phys = os.path.join(save_dir, f"exp_{exp_id}_physical.png")
    plt.savefig(path_phys, dpi=400)
    plt.close()
    print(f"[INFO] Physical graph saved: {path_phys}")

    # ---------------------------
    # 3️Embedding SAT con nodi fisici etichettati
    chain_colors = ['yellow', 'red', 'cyan', 'green', 'orange', 'purple', 'magenta', 'pink', 'brown', 'olive', 'teal', 'navy', 'lime', 'coral',
                    'gold', 'salmon', 'turquoise', 'violet', 'indigo', 'chocolate', 'crimson', 'darkgreen', 'darkblue', 'darkred', 'darkorange'
                    'darkcyan', 'darkmagenta', 'darkgoldenrod', 'darkolivegreen', 'darkslateblue', 'darkturquoise' ]

    phys_to_logical = {}
    # ordina per nodo logico
    for idx, l_node in enumerate(sorted(solution_map.keys(), key=int)):
        chain = solution_map[l_node]
        color = chain_colors[idx % len(chain_colors)]
        for n in chain:
            phys_to_logical[n] = (l_node, color)

    # Colora i nodi fisici in base alla catena logica usando un dizionario
    node_colors_dict = {n: 'lightgray' for n in G_phys.nodes()}
    for n, (_, color) in phys_to_logical.items():
        node_colors_dict[n] = color

    # Etichette = nodo fisico
    labels = {n: str(n) for n in G_phys.nodes()}

    # Archi logici (viola) e catene (rosso)
    used_edges_logical = set()
    used_edges_chains = set()
    for u_log, v_log in G_logical.edges():
        if u_log in solution_map and v_log in solution_map:
            chain_u = solution_map[u_log]
            chain_v = solution_map[v_log]
            for u_phys in chain_u:
                for v_phys in chain_v:
                    if G_phys.has_edge(u_phys, v_phys):
                        used_edges_logical.add(tuple(sorted((u_phys,v_phys))))
    for chain in solution_map.values():
        chain_set = set(chain)
        for u, v in combinations(chain_set, 2):
            if G_phys.has_edge(u, v):
                used_edges_chains.add(tuple(sorted((u, v))))


    edge_colors = []
    edge_widths = []
    for u, v in G_phys.edges():
        e = tuple(sorted((u, v)))
        if e in used_edges_chains:
            edge_colors.append('red')
            edge_widths.append(2.0)
        elif e in used_edges_logical:
            edge_colors.append('purple')
            edge_widths.append(1.5)
        else:
            edge_colors.append('lightgray')
            edge_widths.append(0.4)

    # Disegna embedding finale
    plt.figure(figsize=(8,8))
    nx.draw_networkx_nodes(G_phys, pos_phys,
                        node_color=[node_colors_dict[n] for n in G_phys.nodes()],
                        node_size=120)
    nx.draw_networkx_edges(G_phys, pos_phys, edge_color=edge_colors, width=edge_widths)
    if show_labels:
        nx.draw_networkx_labels(G_phys, pos_phys, labels=labels, font_size=8)
    plt.title(f"Embedding SAT – Experiment {exp_id}")
    plt.axis('off')
    plt.tight_layout()
    path_embed = os.path.join(save_dir, f"exp_{exp_id}_embedding_sat.png")
    plt.savefig(path_embed, dpi=400)
    plt.close()
    print(f"[INFO] SAT embedding plot saved: {path_embed}")
