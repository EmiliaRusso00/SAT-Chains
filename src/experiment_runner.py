import argparse
import time
import yaml
import os

from parser import read_graph, read_graph_json
from cnf_generator import CNFGenerator
from solver_interface_Cripto import solve_dimacs_file
from metrics import write_experiment_output
from utils import ensure_dir
from plot_utils import plot_embedding_results


def run_experiment(cfg, max_attempts=None):
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
    dimacs_path = os.path.join(exp_dir_base, f"exp_{exp_id}.cnf")
    num_vars, num_clauses = gen.generate(dimacs_path)
    time_cnf = time.time() - t0

    # --- Solving SAT ---
    print("[INFO] Solving SAT...")
    total_sat_time = 0.0
    tentativo = 1
    found_any = False
    stopped_early = False

    rev = {vid: (i, idx) for (i, idx), vid in gen.chain_var_map.items()}

    while True:
        if max_attempts is not None and tentativo > max_attempts:
            print(f"[INFO] Stop volontario dopo {max_attempts} tentativi SAT.")
            stopped_early = True
            break

        t_start = time.time()

        threads_to_use = max(os.cpu_count() - 1, 1)
        print(f"[INFO] Using {threads_to_use} threads for MultiThreads")

        res = solve_dimacs_file(
            dimacs_path,
            timeout_seconds=timeout,
            num_threads=threads_to_use)
# Se usi glucose 
#        res = solve_dimacs_file(
#            dimacs_path,
#            timeout_seconds=timeout,
#            cnf_gen=gen
#        )
        sat_one_time = time.time() - t_start
        total_sat_time += sat_one_time

        if res.get("status") != "SAT" or not res.get("model"):
            print("[INFO] Nessun'altra soluzione SAT (UNSAT o timeout).")
            break

        found_any = True

        # --- Directory tentativo ---
        tentativo_dir = os.path.join(exp_dir_base, f"tentativo_{tentativo}")
        ensure_dir(tentativo_dir)

        # --- Ricostruzione soluzione ---
        solution_map = {}
        for lit in res["model"]:
            if lit > 0:
                entry = rev.get(lit)
                if entry is not None:
                    i, chain_idx = entry
                    solution_map[i] = list(gen.valid_chains[i][chain_idx])

        print(f"[SUCCESS] Soluzione SAT trovata → tentativo_{tentativo} "
              f"(tempo SAT: {sat_one_time:.2f}s)")

        # --- Scrittura output ---
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
            solution=[{
                "assignment": solution_map,
                "sat_time": sat_one_time
            }],
            output_dir=tentativo_dir
        )

        # --- Plot ---
        plot_embedding_results(
            G_logical=G_log_json,
            solution_json={"solutions": [{"assignment": solution_map}]},
            save_dir=tentativo_dir,
            exp_id=f"{exp_id}_tentativo_{tentativo}",
            physical_metadata=physical_metadata,
            show_labels=True
        )

        # --- Blocking clause ---
        gen.add_blocking_clause_from_model(res["model"])
        gen.write_dimacs(dimacs_path)

        tentativo += 1

    # --- Output finale UNSAT certificato ---
    if not found_any and not stopped_early:
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
    parser = argparse.ArgumentParser(description="SAT-based graph embedding runner")

    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="File di configurazione YAML"
    )

    parser.add_argument(
        "--max-attempts",
        type=int,
        default=None,
        help="Numero massimo di soluzioni SAT da enumerare "
             "(default: None → fino a UNSAT certificato)"
    )

    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg_all = yaml.safe_load(f)

    ensure_dir("outputs")

    for cfg in cfg_all.get("experiments", []):
        run_experiment(cfg, max_attempts=args.max_attempts)
