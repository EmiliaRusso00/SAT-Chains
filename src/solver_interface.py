import multiprocessing as mp
import time
import traceback
from pysat.solvers import Glucose4
from pysat.formula import CNF

# ================================================================
# PROCESSO SOLVER INDIPENDENTE (WINDOWS SAFE)
# ================================================================
def _solve_process(dimacs_path, cnf_gen, assumptions, return_dict):
    """
    Processo separato per risolvere il DIMACS con timeout sicuro.
    Aggiunge clausole "AND condizionali" tramite aux literal per UNSAT core.
    """
    try:
        cnf = CNF(from_file=dimacs_path)
        solver = Glucose4(use_timer=True)

        # Aggiunge clausole condizionali (¬aux ∨ clause)
        for idx, clause in enumerate(cnf_gen.clauses):
            aux_lit = cnf_gen.num_vars + idx + 1
            solver.add_clause([-aux_lit] + clause)

        # Risoluzione con eventuali assumptions
        sat = solver.solve(assumptions=assumptions)
        model = solver.get_model() if sat else None

        core = solver.get_core() if not sat else None

        solver.delete()

        return_dict["status"] = sat
        return_dict["model"] = model
        return_dict["core"] = core
        return_dict["error"] = None

    except Exception:
        return_dict["status"] = False
        return_dict["model"] = None
        return_dict["core"] = None
        return_dict["error"] = traceback.format_exc()


# ================================================================
# FUNZIONE PUBBLICA PER RISOLVERE FILE DIMACS
# ================================================================
def solve_dimacs_file(dimacs_path, timeout_seconds=None, cnf_gen=None):
    """
    Risolve un file DIMACS con timeout compatibile Windows.
    Ritorna dizionario con:
        - status: "SAT", "UNSAT", "ERROR"
        - model: lista di literal positivi se SAT
        - unsat_core: lista di ID clausole se UNSAT (opzionale)
        - error: stringa errore se fallito
    """
    manager = mp.Manager()
    return_dict = manager.dict()

    # Crea assumptions artificiali per UNSAT core (aux literal)
    assumptions = []
    if cnf_gen:
        assumptions = [cnf_gen.num_vars + idx + 1 for idx, _ in enumerate(cnf_gen.clauses)]

    # Lancia solver in processo separato
    p = mp.Process(target=_solve_process, args=(dimacs_path, cnf_gen, assumptions, return_dict))
    start_time = time.time()
    p.start()
    p.join(timeout_seconds)
    elapsed = time.time() - start_time

    # Timeout
    if p.is_alive():
        p.terminate()
        p.join()
        return {
            "status": "ERROR",
            "time": elapsed,
            "model": None,
            "unsat_core": None,
            "error": "Timeout expired"
        }

    # Estrae risultati
    sat_flag = return_dict.get("status")
    model = return_dict.get("model")
    core = return_dict.get("core")
    error = return_dict.get("error")

    if error:
        return {
            "status": "ERROR",
            "time": elapsed,
            "model": None,
            "unsat_core": None,
            "error": error
        }

    if sat_flag:
        return {
            "status": "SAT",
            "time": elapsed,
            "model": model,
            "unsat_core": None
        }

    # Caso UNSAT
    core_clause_ids = None
    if core and cnf_gen:
        # Traduzione aux literal → indice clausola
        core_clause_ids = [lit - cnf_gen.num_vars - 1 for lit in core if lit > 0]

    return {
        "status": "UNSAT",
        "time": elapsed,
        "model": None,
        "unsat_core": core_clause_ids
    }
