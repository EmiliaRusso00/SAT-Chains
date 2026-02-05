from itertools import combinations
import networkx as nx
import os

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
        self.clauses = []
        self.clause_type = []
        self.clause_set = set()  # per evitare clausole duplicate

    # -------------------------
    def add_clause(self, lits, ctype="generic"):
        key = tuple(sorted(lits))
        if key not in self.clause_set:
            self.clauses.append(list(lits))
            self.clause_type.append(ctype)
            self.clause_set.add(key)

    # -------------------------
    def generate_chain_variables(self):
        """Genera tutte le catene connesse per ogni nodo logico e assegna variabili SAT"""
        self.valid_chains = {}  # nodo logico -> lista di tuple (chain_nodes)
        vid = 1

        default_allowed = self.embedding_constraints.get("default_allowed_expansions", [1])

        for i in self.logical_nodes:
            allowed = self.embedding_constraints.get("per_node", {}).get(i, default_allowed)
            chains = []
            for length in allowed:
                for nodes in combinations(self.physical_nodes, length):
                    if nx.is_connected(self.G_phys.subgraph(nodes)):
                        chains.append(nodes)
            if not chains:
                self.embeddable = False
                self.reject_reasons.append(f"Nessuna catena valida per nodo logico {i}")
                continue
            self.valid_chains[i] = chains

            # assegna variabili SAT per le catene
            for idx, _ in enumerate(chains):
                self.chain_var_map[(i, idx)] = vid
                vid += 1

        self.num_vars = vid - 1

    # -------------------------
    def encode_exactly_one_chain_per_logical(self):
        """Almeno una catena per nodo logico + mutual exclusion tra catene dello stesso nodo"""
        for i, chains in self.valid_chains.items():
            # Almeno una
            lits = [self.chain_var_map[(i, idx)] for idx in range(len(chains))]
            self.add_clause(lits, "at_least_one_chain")

            # Al massimo una
            for idx1, idx2 in combinations(range(len(chains)), 2):
                self.add_clause([-self.chain_var_map[(i, idx1)], -self.chain_var_map[(i, idx2)]],
                                "at_most_one_chain")

    # -------------------------
    def encode_chain_exclusivity(self):
        """Due catene di nodi diversi non possono condividere nodi fisici"""
        for a, b in combinations(self.logical_nodes, 2):
            chains_a = self.valid_chains[a]
            chains_b = self.valid_chains[b]
            for idx_a, chain_a in enumerate(chains_a):
                for idx_b, chain_b in enumerate(chains_b):
                    if set(chain_a) & set(chain_b):
                        # non possono essere entrambe attive
                        self.add_clause([-self.chain_var_map[(a, idx_a)], -self.chain_var_map[(b, idx_b)]],
                                        "chain_exclusivity")

    # -------------------------
    def encode_edge_consistency(self):
        """Edge-consistency: due nodi logici connessi devono avere almeno un arco fisico tra le catene attive"""
        for i, j in self.G_log.edges():
            chains_i = self.valid_chains[i]
            chains_j = self.valid_chains[j]
            for idx_i, chain_i in enumerate(chains_i):
                for idx_j, chain_j in enumerate(chains_j):
                    # se non esiste arco tra catene → proibire entrambe
                    if not any(self.G_phys.has_edge(u, v) for u in chain_i for v in chain_j):
                        self.add_clause([-self.chain_var_map[(i, idx_i)], -self.chain_var_map[(j, idx_j)]],
                                        "edge_consistency")
    def encode_fixed_mappings(self):
        """
        Impone che alcuni nodi logici usino solo catene
        che contengono specifici nodi fisici.
        """
        fixed = self.embedding_constraints.get("fixed_mapping", {})
        if not fixed:
            return

        for i, required_nodes in fixed.items():
            required_nodes = set(required_nodes)

            if i not in self.valid_chains:
                continue

            for idx, chain in enumerate(self.valid_chains[i]):
                # se la catena NON contiene tutti i nodi richiesti → vietala
                if not required_nodes.issubset(set(chain)):
                    self.add_clause(
                        [-self.chain_var_map[(i, idx)]],
                        ctype="fixed_mapping"
                    )

                        
    def add_blocking_clause_from_model(self, model):
        """
        Aggiunge una blocking clause che vieta esattamente
        la selezione corrente delle catene logiche.
        Usa SOLO le variabili di catena.
        """
        # variabili di catena attive nella soluzione
        active_chain_vars = [
            lit for lit in model
            if lit > 0 and lit in self.chain_var_map.values()
        ]

        if not active_chain_vars:
            return False

        # blocking clause: almeno una deve cambiare
        blocking_clause = [-lit for lit in active_chain_vars]
        self.add_clause(blocking_clause, ctype="blocking")
        return True


    # -------------------------
    def generate(self):
        if not self.embeddable:
            print(f"[WARN] Grafo non embeddabile: {self.reject_reasons}")
            return 0, 0
        print("[INFO] Generating chain variables...")
        self.generate_chain_variables()
        print("[INFO] Encoding fixed mappings...")
        self.encode_fixed_mappings()
        print("[INFO] Encoding exactly one chain per logical node...")
        self.encode_exactly_one_chain_per_logical()
        print("[INFO] Encoding chain exclusivity...")
        self.encode_chain_exclusivity()
        print("[INFO] Encoding edge consistency...")
        self.encode_edge_consistency()
        print(f"[INFO] CNF generata: {len(self.clauses)} clausole, {self.num_vars} variabili")
        return self.num_vars, len(self.clauses)

    # -------------------------
    def write_dimacs(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(f"p cnf {self.num_vars} {len(self.clauses)}\n")
            for idx, c in enumerate(self.clauses, start=1):
                f.write(' '.join(str(l) for l in c) + ' 0\n')
        print(f"[INFO] File DIMACS salvato in: {path}")
