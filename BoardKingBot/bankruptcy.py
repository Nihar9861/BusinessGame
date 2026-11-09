"""Bankruptcy: assets go to the creditor (single player) or back to the bank."""
import economy


def declare(game, p, creditor_id=None) -> None:
    active_before = len(game.active_players)
    owned = [t for t, o in game.tile_owner.items() if o == p.id]
    for tid in owned:                      # buildings are sold back to the bank
        h = game.houses.pop(tid, 0)
        if h:
            economy.credit(game, p, h * game.board[tid].house_cost // 2, "buildings liquidated")
    creditor = None
    if creditor_id is not None:
        c = game.player(creditor_id)
        if not c.bankrupt:
            creditor = c
    if creditor:
        if p.cash:
            economy.transfer(game, p, creditor, p.cash, "bankruptcy")
        for tid in owned:
            game.tile_owner[tid] = creditor.id
        creditor.jail_cards += p.jail_cards
        p.jail_cards = 0
        game.emit(f"💀 {p.name} bankrupt! Sab kuch {creditor.name} ko mila.")
    else:
        if p.cash:
            economy.debit(game, p, p.cash, "bankruptcy to bank")
        for tid in owned:
            game.tile_owner.pop(tid, None)
            game.mortgaged.discard(tid)
        from cards import return_jail_card
        for _ in range(p.jail_cards):
            return_jail_card(game)
        p.jail_cards = 0
        game.emit(f"💀 {p.name} bankrupt! Properties bank ko wapas.")
    p.bankrupt = True
    p.in_jail = False
    p.rank = active_before
    game.debt = None
    pt = game.pending_trade
    if pt and p.id in (pt["from"], pt["to"]):
        game.pending_trade = None
