import networkx as nx
import os
from itertools import combinations

class CNFGenerator:

    def __init__(self, G_log, G_phys, embedding_constraints=None,
                 exp_dir=None, exp_id=0):
        self.G_log = G_log
        self.G_phys = G_phys
        self.exp_dir = exp_dir
        self.exp_id = exp_id
        self.embedding_constraints = embedding_constraints or {}

        self.embeddable = True
        self.reject_reasons = []

        self.logical_nodes = list(sorted(G_log.nodes()))
        self.physical_nodes = list(sorted(G_phys.nodes()))
        self.num_vars = 0
        self.chain_var_map = {}   # (logical_node, chain_idx) -> SAT var
        self.valid_chains = {}    # nodo logico -> lista di path
        self.clauses = []         # memorizza tutte le clausole
        self.clause_type = []     # opzionale, utile per debug/analisi

    # -------------------------
    def add_clause(self, lits, ctype="generic"):
        """Aggiunge clausola in memoria"""
        self.clauses.append(list(lits))
        self.clause_type.append(ctype)

    # -------------------------
    def generate_path_chains(self):
        """Genera catene connesse come path e assegna variabili"""
        print("[INFO] Generating path chains for logical nodes...")
        vid = 1
        default_allowed = self.embedding_constraints.get("default_allowed_expansions", [1])

        for i_idx, i in enumerate(self.logical_nodes, start=1):
            print(f"[INFO] Processing logical node {i_idx}/{len(self.logical_nodes)}: {i}")
            allowed = self.embedding_constraints.get("per_node", {}).get(i, default_allowed)
            chains = []

            for length in allowed:
                for start in self.physical_nodes:
                    stack = [(start, (start,))]
                    while stack:
                        node, path = stack.pop()
                        if len(path) == length:
                            chains.append(path)
                            continue
                        for nb in self.G_phys.neighbors(node):
                            if nb not in path:
                                stack.append((nb, path + (nb,)))

            if not chains:
                self.embeddable = False
                self.reject_reasons.append(f"Nessuna catena valida (path) per nodo logico {i}")
                print(f"[WARN] Nessuna catena valida trovata per nodo {i}")
                continue

            chains = list({tuple(sorted(c)) for c in chains})  # rimuovi duplicati
            self.valid_chains[i] = chains

            for idx, _ in enumerate(chains):
                self.chain_var_map[(i, idx)] = vid
                vid += 1

            print(f"[INFO] Logical node {i}: {len(chains)} path chains generated")

        self.num_vars = vid - 1
        print(f"[INFO] Total SAT variables assigned: {self.num_vars}")

    # -------------------------
    def apply_fixed_mapping(self):
        """Applica i vincoli fixed_mapping prima di scrivere le clausole"""
        fixed = self.embedding_constraints.get("fixed_mapping", {})
        if not fixed:
            return

        print("[INFO] Applying fixed mapping constraints...")
        for i, req_nodes in fixed.items():
            req_nodes = set(req_nodes)
            if i not in self.valid_chains:
                continue
            new_chains = []
            for chain in self.valid_chains[i]:
                if req_nodes.issubset(set(chain)):
                    new_chains.append(chain)
            removed = len(self.valid_chains[i]) - len(new_chains)
            self.valid_chains[i] = new_chains
            print(f"[INFO] Logical node {i}: {removed} chains removed due to fixed mapping")
            if not new_chains:
                self.embeddable = False
                self.reject_reasons.append(f"Tutte le catene rimosse per nodo {i} dai vincoli fixed mapping")

    # -------------------------
    def add_blocking_clause_from_model(self, model, dimacs_path=None):
        """
        Aggiunge una blocking clause dal modello SAT per enumerare più soluzioni.
        model: lista di lit positivi/negativi da una soluzione SAT
        dimacs_path: opzionale, scrive subito la clausola anche sul file DIMACS
        """
        # Consideriamo solo le variabili positive della soluzione (quelle assegnate True)
        active_chain_vars = [lit for lit in model if lit > 0 and lit in self.chain_var_map.values()]
        if not active_chain_vars:
            print("[WARN] Nessuna variabile di catena attiva nel modello, skipping blocking clause.")
            return False

        # Negiamo tutte le variabili attive → blocco la stessa soluzione
        blocking_clause = [-lit for lit in active_chain_vars]
        self.add_clause(blocking_clause, ctype="blocking_clause")

        # Aggiorna file DIMACS se fornito
        if dimacs_path:
            with open(dimacs_path, 'r+') as f:
                content = f.read()
                f.seek(0)
                lines = content.splitlines()

                # Incrementa il numero di clausole nell'header
                header = lines[0].split()
                if len(header) >= 4 and header[0] == 'p' and header[1] == 'cnf':
                    num_vars, num_clauses = int(header[2]), int(header[3])
                    num_clauses += 1
                    lines[0] = f"p cnf {num_vars} {num_clauses}"

                # Scrivi la nuova clausola alla fine
                lines.append(' '.join(map(str, blocking_clause)) + ' 0')
                f.write('\n'.join(lines))
        
        print(f"[INFO] Blocking clause added: {blocking_clause}")
        return True

    # -------------------------
    def write_dimacs(self, path):
        """Scrive clausole DIMACS progressivamente su file"""
        if not self.embeddable:
            print(f"[WARN] Grafo non embeddabile: {self.reject_reasons}")
            return 0

        print("[INFO] Writing CNF clauses to DIMACS file...")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        clause_count = 0

        with open(path, 'w') as f:
            f.write(f"p cnf {self.num_vars} 0\n")  # placeholder

            # --- Exactly one chain per logical node ---
            for i_idx, (i, chains) in enumerate(self.valid_chains.items(), start=1):
                lits = [self.chain_var_map[(i, idx)] for idx in range(len(chains))]
                f.write(' '.join(map(str, lits)) + ' 0\n')
                self.add_clause(lits, "exactly_one")
                clause_count += 1
                for idx1, idx2 in combinations(range(len(chains)), 2):
                    lits_excl = [-self.chain_var_map[(i, idx1)], -self.chain_var_map[(i, idx2)]]
                    f.write(' '.join(map(str, lits_excl)) + ' 0\n')
                    self.add_clause(lits_excl, "exactly_one_pairwise")
                    clause_count += 1

            # --- Chain exclusivity ---
            for a, b in combinations(self.logical_nodes, 2):
                chains_a = self.valid_chains[a]
                chains_b = self.valid_chains[b]
                for idx_a, chain_a in enumerate(chains_a):
                    for idx_b, chain_b in enumerate(chains_b):
                        if set(chain_a) & set(chain_b):
                            lits_excl = [-self.chain_var_map[(a, idx_a)], -self.chain_var_map[(b, idx_b)]]
                            f.write(' '.join(map(str, lits_excl)) + ' 0\n')
                            self.add_clause(lits_excl, "chain_exclusivity")
                            clause_count += 1

            # --- Edge consistency ---
            for i, j in self.G_log.edges():
                chains_i = self.valid_chains[i]
                chains_j = self.valid_chains[j]
                for idx_i, chain_i in enumerate(chains_i):
                    for idx_j, chain_j in enumerate(chains_j):
                        if not any(self.G_phys.has_edge(u, v) for u in chain_i for v in chain_j):
                            lits_edge = [-self.chain_var_map[(i, idx_i)], -self.chain_var_map[(j, idx_j)]]
                            f.write(' '.join(map(str, lits_edge)) + ' 0\n')
                            self.add_clause(lits_edge, "edge_consistency")
                            clause_count += 1

        # Aggiorna header
        with open(path, 'r+') as f:
            content = f.read()
            f.seek(0)
            lines = content.splitlines()
            lines[0] = f"p cnf {self.num_vars} {clause_count}"
            f.write('\n'.join(lines))

        print(f"[INFO] DIMACS file written: {path} ({clause_count} clauses)")
        return clause_count

    # -------------------------
    def generate(self, output_path):
        """Genera variabili, applica fixed mapping e scrive CNF"""
        print("[INFO] Starting CNF generation process...")
        self.generate_path_chains()
        self.apply_fixed_mapping()
        if not self.embeddable:
            print("[ERROR] Embedding impossibile dopo fixed mapping")
            return 0, 0
        num_clauses = self.write_dimacs(output_path)
        print("[INFO] CNF generation completed")
        return self.num_vars, num_clauses
