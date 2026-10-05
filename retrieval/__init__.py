"""
Retrieval by pipeline version (registered in the pipeline_versions table):

    v1  vector search only (retrieval/vector.py)
    v2  enhancer (question rewrite + optional SQL) + hybrid search: vector + BM25 merged by RRF
        (retrieval/hybrid.py retrieve_enhanced; generation/enhance.py; retrieval/sql.py)

Every version returns the same Retrieval object, so answering and logging don't care which one ran.
"""
CURRENT_VERSION = "v2"
VERSION_BY_METHOD = {"vector": "v1", "enhanced": "v2"}     # Retrieval.method -> pipeline version


def version_of(retrieval):
    """The pipeline version a Retrieval belongs to (plain "hybrid" is an experiment, not a version)."""
    return VERSION_BY_METHOD[retrieval.method]


def retrieve(question, version=CURRENT_VERSION, **kwargs):
    if version == "v1":
        from retrieval.vector import retrieve as run
    elif version == "v2":
        from retrieval.hybrid import retrieve_enhanced as run
    else:
        raise ValueError(f"unknown pipeline version {version!r}")
    return run(question, **kwargs)
