"""In-memory state for multi-step admin/user flows (FSM)."""

# user_id -> (state, dict)
_states = {}

# Admin states
S_ADDPROD_NAME = "ap_name"
S_ADDPROD_PRICE = "ap_price"
S_ADDPROD_STOCK = "ap_stock"
S_ADDSTOCK = "addstock"
S_PRICE = "price"
S_RENAME = "rename"
S_DESC = "desc"
S_NOTE = "note"
S_WARRANTY = "warranty"
S_HOLD = "hold"
S_SALE = "sale"
S_GIFT = "gift"
S_BROADCAST = "broadcast"
S_SET = "set"
S_ADDBAL = "addbal"
S_SUBBAL = "subbal"
S_LOOKUP = "lookup"
S_BAN = "ban"
S_UNBAN = "unban"
# User states
S_GIFT_REDEEM = "gift_redeem"
S_EMAIL = "email"
S_REGION_TXT = "region_txt"
S_DEP_AMOUNT = "dep_amount"
S_DEP_PROOF = "dep_proof"
S_CRYPTO_CUSTOM = "crypto_custom"
S_QTY_CUSTOM = "qty_custom"
S_STATS_CUSTOM = "stats_custom"
S_DIRPROOF = "dirproof"


def set_state(uid, state, **kw):
    _states[uid] = (state, kw)


def get_state(uid):
    return _states.get(uid, (None, {}))


def clear(uid):
    _states.pop(uid, None)
