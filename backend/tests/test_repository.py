"""Tests du DAL : ventes/COGS, rollback (reverse_sale), cycle-count, FEFO."""
import datetime

import pytest

import models
import repository
import stock


def _restock(db, product, branch, qty, cost):
    return repository.restock_product(
        db, product_id=product.id, branch_id=branch.id, quantity=qty,
        company_id=product.company_id, actor_id=1, unit_cost=cost,
    )


def test_sale_decrements_inventory_and_computes_cogs(db, product, branch):
    _restock(db, product, branch, 50, 2.0)  # WAC = 2.0
    sale = repository.create_sale(
        db,
        {"branch_id": branch.id, "items": [
            {"product_id": product.id, "quantity": 10, "unit_price": 9.0}]},
        company_id=product.company_id, agent_id=1,
    )
    db.refresh(product)
    assert product.total_quantity == 40
    assert sale.total_amount == 90.0
    assert sale.total_cost == 20.0          # 10 * WAC(2.0)
    assert sale.items[0].unit_cost == 2.0


def test_sale_rejects_insufficient_stock(db, product, branch):
    _restock(db, product, branch, 5, 1.0)
    with pytest.raises(ValueError):
        repository.create_sale(
            db,
            {"branch_id": branch.id, "items": [
                {"product_id": product.id, "quantity": 99, "unit_price": 9.0}]},
            company_id=product.company_id, agent_id=1,
        )
    db.refresh(product)
    assert product.total_quantity == 5      # inchangé (transaction annulée)


def test_reverse_sale_restores_stock_and_marks_reversed(db, product, branch):
    _restock(db, product, branch, 30, 1.0)
    sale = repository.create_sale(
        db,
        {"branch_id": branch.id, "items": [
            {"product_id": product.id, "quantity": 12, "unit_price": 5.0}]},
        company_id=product.company_id, agent_id=1,
    )
    db.refresh(product)
    assert product.total_quantity == 18
    reversed_sale = repository.reverse_sale(
        db, sale_id=sale.id, company_id=product.company_id, actor_id=1,
    )
    db.refresh(product)
    assert reversed_sale.status == "REVERSED"
    assert product.total_quantity == 30     # stock réintégré
    # Mouvement de compensation présent (IN positif).
    movements = repository.get_movements(db, product.company_id)
    assert any(m.movement_type == "IN" and "Annulation" in (m.reason or "") for m in movements)


def test_reverse_sale_twice_rejected(db, product, branch):
    _restock(db, product, branch, 10, 1.0)
    sale = repository.create_sale(
        db,
        {"branch_id": branch.id, "items": [
            {"product_id": product.id, "quantity": 2, "unit_price": 5.0}]},
        company_id=product.company_id, agent_id=1,
    )
    repository.reverse_sale(db, sale_id=sale.id, company_id=product.company_id, actor_id=1)
    with pytest.raises(ValueError):
        repository.reverse_sale(db, sale_id=sale.id, company_id=product.company_id, actor_id=1)


def test_cycle_count_positive_and_negative_variance(db, product, branch):
    _restock(db, product, branch, 20, 1.0)
    # Comptage révèle un manquant : 17 au lieu de 20 -> variance -3
    res = repository.adjust_inventory(
        db, product_id=product.id, branch_id=branch.id, counted_quantity=17,
        company_id=product.company_id, actor_id=1,
    )
    assert res["system_before"] == 20
    assert res["variance"] == -3
    db.refresh(product)
    assert product.total_quantity == 17

    # Comptage révèle un excédent : 25 -> variance +8
    res2 = repository.adjust_inventory(
        db, product_id=product.id, branch_id=branch.id, counted_quantity=25,
        company_id=product.company_id, actor_id=1,
    )
    assert res2["variance"] == 8
    db.refresh(product)
    assert product.total_quantity == 25
    # Mouvement ADJUST tracé.
    movements = repository.get_movements(db, product.company_id)
    assert any(m.movement_type == "ADJUST" for m in movements)


def test_cycle_count_no_variance_is_noop(db, product, branch):
    _restock(db, product, branch, 10, 1.0)
    res = repository.adjust_inventory(
        db, product_id=product.id, branch_id=branch.id, counted_quantity=10,
        company_id=product.company_id, actor_id=1,
    )
    assert res["variance"] == 0
    assert res["movement_id"] is None


def test_cycle_count_rejects_negative_count(db, product, branch):
    _restock(db, product, branch, 10, 1.0)
    with pytest.raises(ValueError):
        repository.adjust_inventory(
            db, product_id=product.id, branch_id=branch.id, counted_quantity=-1,
            company_id=product.company_id, actor_id=1,
        )


def test_fefo_consumes_earliest_expiry_first(db, product, branch):
    now = datetime.datetime.now(datetime.timezone.utc)
    # Lot A expire bientôt, Lot B plus tard. On reçoit B d'abord pour vérifier FEFO (pas FIFO).
    _restock_with_lot(db, product, branch, 5, "B-late", now + datetime.timedelta(days=60))
    _restock_with_lot(db, product, branch, 5, "A-soon", now + datetime.timedelta(days=5))
    # Consomme 6 unités : doit vider A-soon (5) puis entamer B-late (1).
    picks = stock.consume_lots_fefo(db, product.id, branch.id, 6)
    db.commit()
    lots = {l.lot_number: l.quantity for l in db.query(models.Lot).all()}
    assert lots["A-soon"] == 0
    assert lots["B-late"] == 4
    assert sum(p["qty"] for p in picks) == 6


def _restock_with_lot(db, product, branch, qty, lot_number, expiry):
    return repository.restock_product(
        db, product_id=product.id, branch_id=branch.id, quantity=qty,
        company_id=product.company_id, actor_id=1, unit_cost=1.0,
        lot_number=lot_number, expiry_date=expiry,
    )
