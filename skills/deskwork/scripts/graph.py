"""The dependency graph, and the three questions asked of it.

A cycle is reported as a cycle. It is never broken arbitrarily to produce an
order, because a plausible order that is wrong is worse than no order.
"""


class Graph:
    def __init__(self, edges, closed=None):
        self.closed = set(closed or ())
        self.edges = {
            node: {b for b in blockers if b not in self.closed}
            for node, blockers in edges.items()
            if node not in self.closed
        }
        for blockers in list(self.edges.values()):
            for blocker in blockers:
                self.edges.setdefault(blocker, set())

    def ready(self):
        return sorted(
            (n for n, blockers in self.edges.items() if not blockers),
            key=lambda r: (r.owner, r.repo, int(r.number)),
        )

    def blocked(self):
        return sorted(
            (n for n, blockers in self.edges.items() if blockers),
            key=lambda r: (r.owner, r.repo, int(r.number)),
        )

    def bottlenecks(self, threshold=3):
        counts = {}
        for blockers in self.edges.values():
            for blocker in blockers:
                counts[blocker] = counts.get(blocker, 0) + 1
        found = [(n, c) for n, c in counts.items() if c >= threshold]
        return sorted(found, key=lambda pair: (-pair[1], pair[0].owner, pair[0].repo, int(pair[0].number)))

    def cycles(self):
        """Tarjan's strongly connected components. Any component above one node
        is a cycle, and so is any single node that blocks itself."""
        index = {}
        low = {}
        stack = []
        on_stack = set()
        found = []
        counter = [0]

        def visit(node):
            index[node] = low[node] = counter[0]
            counter[0] += 1
            stack.append(node)
            on_stack.add(node)
            for blocker in self.edges.get(node, ()):
                if blocker not in index:
                    visit(blocker)
                    low[node] = min(low[node], low[blocker])
                elif blocker in on_stack:
                    low[node] = min(low[node], index[blocker])
            if low[node] == index[node]:
                component = []
                while True:
                    other = stack.pop()
                    on_stack.discard(other)
                    component.append(other)
                    if other == node:
                        break
                if len(component) > 1 or node in self.edges.get(node, ()):
                    found.append(component)

        for node in self.edges:
            if node not in index:
                visit(node)
        sorted_components = [
            sorted(c, key=lambda r: (r.owner, r.repo, int(r.number)))
            for c in found
        ]
        return sorted(sorted_components, key=lambda c: (c[0].owner, c[0].repo, int(c[0].number)))
