"""Domain test packs. Each pack is reported as its own tier category.

To add a pack: create a module with a list of TestcaseSeed(pack="<name>", ...)
and register it here.
"""
from app.evals.packs.financial_services import FINANCIAL_SERVICES, PACK as _FS

DOMAIN_PACKS = {
    _FS: FINANCIAL_SERVICES,
}
