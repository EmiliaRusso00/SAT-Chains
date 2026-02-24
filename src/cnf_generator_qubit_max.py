import networkx as nx
from itertools import combinations, product
import os

class CNFGenerator:

    def __init__(self, G_log, G_phys, embedding_constraints=None,
                 exp_dir=None, exp_id=0):

        self.G_log = G_log
        self.G_phys = G_phys
        self.embedding_constraints = embedding_constraints or {}

        self.exp_dir = exp_dir or "."
        self.exp_id = exp_id

        self.embeddable = True
        self.reject_reasons = []

        self.logical_nodes = sorted(G_log.nodes())
        self.physical_nodes = sorted(G_phys.nodes())

        self.valid_chains = {}        # i -> list of components
        self.chain_var_map = {}       # (i, idx) -> var
        self.num_vars = 0

        self.clauses = []

        # massimo numero totale di qubit
        self.max_total_qubits = self.embedding_constraints.get("max_total_qubits", None)

    # --------------------------------------------------
    # Clause helper
    # --------------------------------------------------
    def add_clause(self, lits):
        self.clauses.append(list(lits))
        print(f"[CLAUSE ADDED] {lits}")

    # --------------------------------------------------
    # Generate CONNECTED chains respecting default, per_node, fixed_mapping
    # --------------------------------------------------
    def generate_connected_chains(self):
        print("[INFO] Generating connected chains...")
        vid = 1
        default_sizes = self.embedding_constraints.get(
            "default_allowed_expansions", [1]
        )

        per_node = self.embedding_constraints.get("per_node", {})
        fixed = self.embedding_constraints.get("fixed_mapping", {})

        for i in self.logical_nodes:
            allowed_sizes = per_node.get(i, default_sizes)
            required = set(fixed.get(i, []))

            chains = []

            for size in allowed_sizes:
                for subset in combinations(self.physical_nodes, size):
                    S = set(subset)
                    if not required.issubset(S):
                        continue
                    if nx.is_connected(self.G_phys.subgraph(S)):
                        chains.append(tuple(sorted(S)))

            if not chains:
                self.embeddable = False
                self.reject_reasons.append(
                    f"Nessuna chain valida per nodo logico {i}"
                )
                print(f"[UNSAT] Nodo logico {i} non ha chain valide!")
                return

            self.valid_chains[i] = chains
            for idx in range(len(chains)):
                self.chain_var_map[(i, idx)] = vid
                vid += 1

            print(f"[INFO] Nodo logico {i} chains generate: {chains}")

        self.num_vars = vid - 1
        print(f"[INFO] Total variables: {self.num_vars}")

    # --------------------------------------------------
    # CNF encoding
    # --------------------------------------------------
    def encode_exactly_one(self):
        print("[INFO] Encoding exactly-one clauses...")
        for i, chains in self.valid_chains.items():
            vars_i = [
                self.chain_var_map[(i, idx)]
                for idx in range(len(chains))
            ]
            # almeno una chain
            self.add_clause(vars_i)
            # al massimo una chain
            for a, b in combinations(vars_i, 2):
                self.add_clause([-a, -b])
        print(f"[INFO] Exactly-one encoding completed for {len(self.valid_chains)} nodes.")

    def encode_chain_exclusivity(self):
        print("[INFO] Encoding chain exclusivity...")
        for i, j in combinations(self.logical_nodes, 2):
            for idx_i, C in enumerate(self.valid_chains[i]):
                setC = set(C)
                v_i = self.chain_var_map[(i, idx_i)]
                for idx_j, D in enumerate(self.valid_chains[j]):
                    if setC & set(D):
                        v_j = self.chain_var_map[(j, idx_j)]
                        self.add_clause([-v_i, -v_j])
        print("[INFO] Chain exclusivity encoding completed.")

    def encode_edge_consistency(self):
        print("[INFO] Encoding edge consistency...")
        for i, j in self.G_log.edges():
            for idx_i, C in enumerate(self.valid_chains[i]):
                v_i = self.chain_var_map[(i, idx_i)]
                for idx_j, D in enumerate(self.valid_chains[j]):
                    v_j = self.chain_var_map[(j, idx_j)]
                    if not any(
                        self.G_phys.has_edge(u, v)
                        for u in C for v in D
                    ):
                        self.add_clause([-v_i, -v_j])
        print("[INFO] Edge consistency encoding completed.")

    # --------------------------------------------------
    # Vincolo globale: max_total_qubits
    # --------------------------------------------------
    def encode_max_total_qubits(self):
        if self.max_total_qubits is None:
            return

        print(f"[INFO] Encoding max_total_qubits ≤ {self.max_total_qubits}...")
        Q = self.max_total_qubits

        # Lista di variabili per nodo logico
        vars_per_node = [
            [self.chain_var_map[(i, idx)] for idx in range(len(self.valid_chains[i]))]
            for i in self.logical_nodes
        ]

        # Generiamo tutte le combinazioni uniche di una catena per nodo logico
        for selection in product(*vars_per_node):
            # calcoliamo il totale dei qubit
            total_qubits = sum(
                len(self.valid_chains[self.logical_nodes[node_idx]][
                    vars_per_node[node_idx].index(var)
                ]) for node_idx, var in enumerate(selection)
            )
            if total_qubits > Q:
                clause = [-v for v in selection]
                self.add_clause(clause)
                print(f"[INFO] Blocking combination {selection} → total qubits {total_qubits} > {Q}")

        print("[INFO] max_total_qubits encoding completed.")

    # --------------------------------------------------
    # Blocking clause
    # --------------------------------------------------
    def add_blocking_clause_from_model(self, model, dimacs_path=None):
        active_chain_vars = [lit for lit in model if lit > 0 and lit in self.chain_var_map.values()]
        if not active_chain_vars:
            return False
        blocking_clause = [-lit for lit in active_chain_vars]
        self.add_clause(blocking_clause)
        print(f"[INFO] Blocking clause added from model: {blocking_clause}")
        if dimacs_path:
            with open(dimacs_path, 'r+') as f:
                content = f.read()
                f.seek(0)
                lines = content.splitlines()
                header = lines[0].split()
                if len(header) >= 4 and header[0] == 'p' and header[1] == 'cnf':
                    num_vars, num_clauses = int(header[2]), int(header[3])
                    num_clauses += 1
                    lines[0] = f"p cnf {num_vars} {num_clauses}"
                lines.append(' '.join(map(str, blocking_clause)) + ' 0')
                f.write('\n'.join(lines))
        return True

    # --------------------------------------------------
    # DIMACS
    # --------------------------------------------------
    def write_dimacs(self, path):
        print(f"[INFO] Writing DIMACS to {path}...")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(f"p cnf {self.num_vars} {len(self.clauses)}\n")
            for c in self.clauses:
                f.write(" ".join(map(str, c)) + " 0\n")
        print("[INFO] DIMACS file written.")

    # --------------------------------------------------
    # Main
    # --------------------------------------------------
    def generate(self, output_path):
        print("[INFO] Starting CNF generation...")
        self.generate_connected_chains()
        if not self.embeddable:
            print("[UNSAT at generation]", self.reject_reasons)
            return 0, 0

        self.encode_exactly_one()
        self.encode_chain_exclusivity()
        self.encode_edge_consistency()
        self.encode_max_total_qubits()  # ← vincolo globale

        print(f"[INFO] CNF generation completed: {self.num_vars} vars, {len(self.clauses)} clauses")
        self.write_dimacs(output_path)
        return self.num_vars, len(self.clauses)