"""Explicit method support and uniform study admission, independent of inputs."""
from dataclasses import asdict, dataclass

from hponas.encoding import as_knob_space


@dataclass(frozen=True)
class SearcherCapabilities:
    kinds: tuple[str, ...]
    conditionals: bool = False
    objectives: str = 'scalar'
    constraints: bool = False
    partial_fidelity: bool = False
    architecture_coordinates: bool = True
    prior: str = 'none'
    concurrent_proposals: bool = True
    joint_batch: bool = False
    max_dimensions: int | None = None
    failed_observations: bool = True

    def __post_init__(self):
        if (not isinstance(self.kinds, tuple) or not self.kinds
                or len(set(self.kinds)) != len(self.kinds)
                or not set(self.kinds) <= {'continuous', 'ordinal', 'categorical'}):
            raise ValueError('Explicit supported knob kinds required')
        if self.objectives not in {'scalar', 'vector'} or self.prior not in {'none', 'external_law', 'density_function'}:
            raise ValueError('Unknown objective or prior capability')
        for name in ('conditionals', 'constraints', 'partial_fidelity', 'architecture_coordinates',
                     'concurrent_proposals', 'joint_batch', 'failed_observations'):
            if type(getattr(self, name)) is not bool:
                raise ValueError('Capability flags must be boolean')
        if self.max_dimensions is not None and (type(self.max_dimensions) is not int or self.max_dimensions < 1):
            raise ValueError('Positive dimension support limit required')

    @property
    def contract(self):
        return {**asdict(self), 'kinds': list(self.kinds), 'version': 1}

    def report(self):
        return {'support_contract': self.contract, 'parameter_types': list(self.kinds),
                'knob_kinds': list(self.kinds), 'conditionals': self.conditionals,
                'multi_objective': self.objectives == 'vector', 'supports_constraints': self.constraints,
                'supports_fidelity': self.partial_fidelity, 'prior': self.prior != 'none',
                'max_dim': self.max_dimensions, 'supports_batch': self.joint_batch}


MIXED = ('continuous', 'ordinal', 'categorical')


def admit(searcher, *, scheduler, workers, declared, architecture=()):
    support = getattr(searcher, 'support', None)
    if support is None:
        if declared or architecture:
            raise ValueError('Declared Study requires explicit searcher capabilities')
        return {'status': 'legacy_unverified_capabilities'}
    if not isinstance(support, SearcherCapabilities):
        raise ValueError('Searcher support must be a SearcherCapabilities contract')
    if support.joint_batch and not callable(getattr(searcher, 'suggest_batch', None)):
        raise ValueError('Joint batch capability requires a batch proposal interface')
    space = as_knob_space(searcher.search_space)
    if not {k.kind for k in space.knobs} <= set(support.kinds):
        raise ValueError('Searcher does not support these parameter kinds')
    if any(k.condition is not None for k in space.knobs) and not support.conditionals:
        raise ValueError('Searcher does not support conditional coordinates')
    if any(k.prior is not None for k in space.knobs):
        raise ValueError('Knob.prior is documentation only; configure an explicit supported prior law')
    if support.max_dimensions is not None and space.dim > support.max_dimensions:
        raise ValueError('Searcher dimension support limit exceeded')
    vector = getattr(searcher, 'multi_objective_spec', None)
    if (support.objectives == 'vector') != (vector is not None):
        raise ValueError('Searcher objective capability differs from its configured contract')
    if vector is not None and vector.contract['constraints'] and not support.constraints:
        raise ValueError('Searcher does not support constraint measurements')
    if scheduler is not None and not support.partial_fidelity:
        raise ValueError('Searcher does not support partial-fidelity Study observations')
    if workers > 1 and not support.concurrent_proposals:
        raise ValueError('Searcher requires sequential proposals')
    if declared and not support.failed_observations:
        raise ValueError('Declared Study requires retained failed-observation support')
    if (not isinstance(architecture, (tuple, list)) or any(not isinstance(x, str) for x in architecture)
            or len(architecture) != len(set(architecture)) or not set(architecture) <= {k.name for k in space.knobs}):
        raise ValueError('Architecture coordinates must name distinct search-space knobs')
    if architecture and not support.architecture_coordinates:
        raise ValueError('Searcher does not support architecture coordinates')
    return {'status': 'admitted', 'contract': support.contract, 'architecture_coordinates': list(architecture),
            'scope': 'coordinate search only; constructed model semantics remain caller-owned'}
