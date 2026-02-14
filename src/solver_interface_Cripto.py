import multiprocessing as mp
import subprocess
import time
import traceback
import os


def _solve_process(dimacs_path, return_dict, num_threads):
    try:
#        cmd = [
#            "../../lingeling/plingeling",
#            "-t", str(max(num_threads, 1)),
#            dimacs_path
#        ]
#
        cmd = [
            "../../kissat/build/kissat",
            f"--threads={max(num_threads, 1)}",
            dimacs_path
        ]
        
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        out = proc.stdout
        err = proc.stderr

        # stampa prime linee per confermare thread
        # --- STAMPA TUTTO L'OUTPUT PER DEBUG ---
        print("Plingeling output (full):")
        print(out)  # ora vedrai anche la linea c - W ... USING 4 WORKER THREADS

        # --- SAT ---
        if "s SATISFIABLE" in out:
            model = []
            for line in out.splitlines():
                if line.startswith("v "):
                    model.extend(
                        int(x) for x in line.split()[1:]
                        if x != "0"
                    )

            return_dict["status"] = True
            return_dict["model"] = model
            return_dict["error"] = None
            return

        # --- UNSAT ---
        if "s UNSATISFIABLE" in out:
            return_dict["status"] = False
            return_dict["model"] = None
            return_dict["error"] = None
            return

        # --- UNKNOWN / ERROR ---
        return_dict["status"] = False
        return_dict["model"] = None
        return_dict["error"] = out + "\n" + err

    except Exception:
        return_dict["status"] = False
        return_dict["model"] = None
        return_dict["error"] = traceback.format_exc()


def solve_dimacs_file(dimacs_path, timeout_seconds=None, num_threads=None):
    """
    Risolve un file DIMACS usando Plingeling (vero multithread).
    Funziona su Linux e Windows.
    """
    if num_threads is None:
        num_threads = max(os.cpu_count() - 1, 1)

    manager = mp.Manager()
    return_dict = manager.dict()

    p = mp.Process(
        target=_solve_process,
        args=(dimacs_path, return_dict, num_threads)
    )

    start = time.time()
    p.start()
    p.join(timeout_seconds)
    elapsed = time.time() - start

    # --- TIMEOUT ---
    if p.is_alive():
        p.terminate()
        p.join()
        return {
            "status": "ERROR",
            "time": elapsed,
            "model": None,
            "error": "Timeout expired"
        }

    # --- ERRORE ---
    if return_dict.get("error"):
        return {
            "status": "ERROR",
            "time": elapsed,
            "model": None,
            "error": return_dict["error"]
        }

    # --- RISULTATO ---
    return {
        "status": "SAT" if return_dict.get("status") else "UNSAT",
        "time": elapsed,
        "model": return_dict.get("model")
    }
    