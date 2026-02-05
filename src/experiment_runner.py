import argparse
import time
import yaml
import os

from parser import read_graph, read_graph_json
from cnf_generator import CNFGenerator
from solver_interface import solve_dimacs_file
from metrics import write_experiment_output
from utils import ensure_dir
from plot_utils import plot_embedding_results


def run_experiment(cfg):
    exp_id = cfg.get("id", 0)
    print(f"\n[INFO] Running experiment ID: {exp_id}")

    # --- Directory base esperimento ---
    exp_dir_base = os.path.join("outputs", str(exp_id))
    ensure_dir(exp_dir_base)

    # --- Caricamento grafi ---
    G_logical = read_graph(cfg["logical_graph"])
    G_physical = read_graph(cfg["physical_graph"])
    G_log_json, logical_metadata = read_graph_json(cfg.get("logical_graph_json"))
    G_phys_json, physical_metadata = read_graph_json(cfg.get("physical_graph_json"))

    timeout = cfg.get("timeout_seconds", None)
    max_solutions = cfg.get("max_solutions", 40)

    # --- CNF Generator ---
    gen = CNFGenerator(
        G_log=G_logical,
        G_phys=G_physical,
        embedding_constraints=cfg.get("embedding_constraints"),
        exp_dir=exp_dir_base,
        exp_id=exp_id
    )

    if not gen.embeddable:
        print("[ERROR] Embedding impossibile.")
        return

    # --- Generazione CNF ---
    print("[INFO] Generating CNF...")
    t0 = time.time()
    num_vars, num_clauses = gen.generate()
    time_cnf = time.time() - t0

    dimacs_path = os.path.join(exp_dir_base, f"exp_{exp_id}.cnf")
    gen.write_dimacs(dimacs_path)

    # --- Solving multi-soluzione ---
    print(f"[INFO] Solving SAT (max {max_solutions} tentativi)...")
    total_sat_time = 0.0
    rev = {vid: (i, idx) for (i, idx), vid in gen.chain_var_map.items()}
    found_any = False

    for k in range(1, max_solutions + 1):
        t_start = time.time()
        res = solve_dimacs_file(
            dimacs_path,
            timeout_seconds=timeout,
            cnf_gen=gen
        )
        sat_one_time = time.time() - t_start
        total_sat_time += sat_one_time

        if res.get("status") != "SAT" or not res.get("model"):
            print("[INFO] Nessun'altra soluzione SAT.")
            break

        found_any = True
        tentativo_dir = os.path.join(exp_dir_base, f"tentativo_{k}")
        ensure_dir(tentativo_dir)

        # --- Ricostruzione soluzione ---
        solution_map = {}
        for lit in res["model"]:
            if lit > 0:
                entry = rev.get(lit)
                if entry is not None:
                    i, chain_idx = entry
                    chain_nodes = gen.valid_chains[i][chain_idx]
                    solution_map[i] = list(chain_nodes)

        print(f"[SUCCESS] Soluzione SAT trovata → tentativo_{k} (tempo SAT: {sat_one_time:.2f}s)")

        # --- Scrittura output per tentativo ---
        write_experiment_output(
            exp_id=exp_id,
            config=cfg,
            logical_graph=G_logical,
            physical_graph=G_physical,
            num_vars=num_vars,
            num_clauses=len(gen.clauses),
            encoding_type="pairwise",
            solver_name="glucose",
            time_cnf=time_cnf,
            time_sat=sat_one_time,
            status="SAT",
            solution=[{"assignment": solution_map, "sat_time": sat_one_time}],
            output_dir=tentativo_dir
        )

        # --- Plot per tentativo ---
        plot_embedding_results(
            G_logical=G_log_json,
            solution_json={"solutions": [{"assignment": solution_map}]},
            save_dir=tentativo_dir,
            exp_id=f"{exp_id}_tentativo_{k}",
            physical_metadata=physical_metadata,
            show_labels=True
        )

        # --- Blocking clause per prossima soluzione ---
        gen.add_blocking_clause_from_model(res["model"])
        gen.write_dimacs(dimacs_path)

    if not found_any:
        # output UNSAT a livello di esperimento
        write_experiment_output(
            exp_id=exp_id,
            config=cfg,
            logical_graph=G_logical,
            physical_graph=G_physical,
            num_vars=num_vars,
            num_clauses=len(gen.clauses),
            encoding_type="pairwise",
            solver_name="glucose",
            time_cnf=time_cnf,
            time_sat=total_sat_time,
            status="UNSAT",
            solution=None,
            output_dir=exp_dir_base
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="config.yaml")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        cfg_all = yaml.safe_load(f)

    ensure_dir("outputs")

    for cfg in cfg_all.get("experiments", []):
        run_experiment(cfg)
