"""Parallel independent architecture stores with one coordinator per store."""
from concurrent.futures import ThreadPoolExecutor
from hponas.population_parallel import run_batch


def run_candidates(generation, alive, target, executor):
    # Coordinator threads only perform atomic local journal operations; the
    # shared ResourceExecutor bounds the actual numerical workers.
    executor.prepare()
    def one(index):
        return run_batch(generation._store(index),[generation._request(index,target)],executor)[0]
    with ThreadPoolExecutor(max_workers=executor.num_workers) as pool:
        return dict(zip(alive,pool.map(one,alive)))
