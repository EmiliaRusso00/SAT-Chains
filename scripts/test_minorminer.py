import json
import time
import yaml
import os
import copy
import networkx as nx
import minorminer
from collections import Counter

# ---------------------------------------------------------
# CARICATORE GRAFO JSON
# ---------------------------------------------------------
def load_graph_json(path):
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

    if "metadata" in data:
        G.graph.update(data["metadata"])

    return G

# ---------------------------------------------------------
# CALCOLO ARCHI FISICI USATI
# ---------------------------------------------------------
def compute_used_physical_edges(G_logical, G_physical, embedding):
    physical_edges_logical = set()
    physical_edges_chain = set()

    for u, v in G_logical.edges():
        if u not in embedding or v not in embedding:
            continue
        for pu in embedding[u]:
            for pv in embedding[v]:
                if G_physical.has_edge(pu, pv):
                    physical_edges_logical.add(tuple(sorted((pu, pv))))

    for chain in embedding.values():
        chain = list(chain)
        for i in range(len(chain)):
            for j in range(i + 1, len(chain)):
                if G_physical.has_edge(chain[i], chain[j]):
                    physical_edges_chain.add(tuple(sorted((chain[i], chain[j]))))

    return physical_edges_logical, physical_edges_chain

# ---------------------------------------------------------
# VERIFICA ARCHI LOGICI
# ---------------------------------------------------------
def respects_logical_edges(G_logical, embedding, G_physical):
    for u, v in G_logical.edges():
        if u not in embedding or v not in embedding:
            return False
        if not any(G_physical.has_edge(a, b) for a in embedding[u] for b in embedding[v]):
            return False
    return True

# ---------------------------------------------------------
# COMPARAZIONE EMBEDDING
# ---------------------------------------------------------
def better_embedding(a, b):
    if not a["success"]:
        return False
    if b is None:
        return True
    if a["num_physical_used"] != b["num_physical_used"]:
        return a["num_physical_used"] < b["num_physical_used"]
    if a["max_chain_length"] != b["max_chain_length"]:
        return a["max_chain_length"] < b["max_chain_length"]
    if a["avg_chain_length"] != b["avg_chain_length"]:
        return a["avg_chain_length"] < b["avg_chain_length"]
    return a["time_seconds"] < b["time_seconds"]

# ---------------------------------------------------------
# RUN MINORMINER (LOGICA INVARIATA)
# ---------------------------------------------------------
def run_minorminer(G_logical, G_physical, exp, mode, out_dir, attempt, max_attempts):
    start = time.perf_counter()

    embedding = minorminer.find_embedding(
        G_logical.edges(),
        G_physical.edges(),
        timeout=exp.get("timeout_seconds", 30)
    )

    elapsed = time.perf_counter() - start
    success = bool(embedding) and respects_logical_edges(
        G_logical, embedding, G_physical
    )

    attempt_str = f"{attempt}/{max_attempts}"

    if success:
        max_chain = max(len(c) for c in embedding.values())
        num_phys_used = len(set().union(*embedding.values()))
        print(
            f"[MM Success {attempt_str} | {mode.upper()}] "
            f"Max chain: {max_chain} | Num fisici usati: {num_phys_used} | "
            f"Tempo: {elapsed:.4f}s"
        )
    else:
        print(f"[MM Fail {attempt_str} | {mode.upper()}] Embedding non valido.")

    result = {
        "experiment_id": exp["id"],
        "mode": mode,
        "success": success,
        "time_seconds": elapsed,
        "num_logical_nodes": G_logical.number_of_nodes(),
        "num_physical_nodes": G_physical.number_of_nodes(),
        "num_physical_used": None,
        "embedding": {},
        "max_chain_length": None,
        "avg_chain_length": None,
        "physical_edges_logical": [],
        "physical_edges_chain": [],

        # --- NUOVI CAMPI ---
        "chain_lengths_per_node": {},
        "chain_length_distribution": {}
    }

    if success:
        used_physical_nodes = set()
        for chain in embedding.values():
            used_physical_nodes.update(chain)

        chains = list(embedding.values())
        lengths = [len(c) for c in chains]

        result["embedding"] = {str(k): list(v) for k, v in embedding.items()}
        result["num_physical_used"] = len(used_physical_nodes)
        result["max_chain_length"] = max(lengths)
        result["avg_chain_length"] = sum(lengths) / len(lengths)

        logical_edges, chain_edges = compute_used_physical_edges(
            G_logical, G_physical, embedding
        )
        result["physical_edges_logical"] = list(logical_edges)
        result["physical_edges_chain"] = list(chain_edges)

        # -----------------------------
        # RIFERIMENTI CATENE PER NODO
        # -----------------------------
        chain_lengths_per_node = {
            str(k): len(v) for k, v in embedding.items()
        }

        result["chain_lengths_per_node"] = chain_lengths_per_node
        result["chain_length_distribution"] = dict(
            Counter(chain_lengths_per_node.values())
        )

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "minorminer_result.json"), "w") as f:
        json.dump(result, f, indent=2)

    return result

# ---------------------------------------------------------
# MAIN PER TEST FULL (INVARIATO)
# ---------------------------------------------------------
def main():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    experiments = config["experiments"]
    output_base = config.get("output_dir", "outputs")

    summary = []

    for exp in experiments:
        exp_id = exp["id"]
        print(f"\n=== ESPERIMENTO {exp_id} ===")

        G_logical = load_graph_json(exp["logical_graph_json"])
        G_physical_full = load_graph_json(exp["physical_graph_json"])

        max_attempts = exp.get("max_attempts", 50)
        full_attempts = 0
        full_time_accum = 0.0
        best_full = None
        full_first_success = None
        full_done = False
        iter_count = 0

        while not full_done and iter_count < max_attempts:
            iter_count += 1
            full_attempts += 1

            res = run_minorminer(
                G_logical, G_physical_full, exp, "full",
                os.path.join(output_base, str(exp_id), "full"),
                attempt=full_attempts,
                max_attempts=max_attempts
            )

            full_time_accum += res["time_seconds"]

            if res["success"] and better_embedding(res, best_full):
                best_full = copy.deepcopy(res)

            if res["success"] and res["max_chain_length"] == 1:
                full_first_success = copy.deepcopy(res)
                full_first_success["time_to_1to1"] = full_time_accum
                full_first_success["time_single_run_1to1"] = res["time_seconds"]
                full_first_success["attempts_to_1to1"] = full_attempts
                full_done = True

        final_full = full_first_success if full_first_success else best_full

        if final_full:
            out_dir_full = os.path.join(output_base, str(exp_id), "minorminer")
            os.makedirs(out_dir_full, exist_ok=True)
            with open(os.path.join(out_dir_full, "minorminer_result.json"), "w") as f:
                json.dump(final_full, f, indent=2)

        summary.append({
            "experiment_id": exp_id,
            "full": {
                "total_attempts": full_attempts,
                "found_1to1": bool(full_first_success)
            }
        })

    with open(os.path.join(output_base, "minorminer_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== TEST FULL COMPLETATO ===")

if __name__ == "__main__":
    main()
