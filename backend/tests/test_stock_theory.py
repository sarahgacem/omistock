"""Tests théorie de gestion de stock : WAC, ROP, alertes, valorisation, EOQ."""
import stock


def test_weighted_average_cost_on_two_receipts(db, product, branch):
    import repository

    # Réception 1 : 100 @ 1.00
    repository.restock_product(
        db, product_id=product.id, branch_id=branch.id, quantity=100,
        company_id=product.company_id, actor_id=1, unit_cost=1.00,
    )
    db.refresh(product)
    assert product.cost_price == 1.00
    assert product.total_quantity == 100

    # Réception 2 : 100 @ 2.00 -> WAC = (100*1 + 100*2)/200 = 1.50
    repository.restock_product(
        db, product_id=product.id, branch_id=branch.id, quantity=100,
        company_id=product.company_id, actor_id=1, unit_cost=2.00,
    )
    db.refresh(product)
    assert product.cost_price == 1.50
    assert product.total_quantity == 200


def test_wac_unchanged_when_cost_missing(db, product, branch):
    import repository
    repository.restock_product(
        db, product_id=product.id, branch_id=branch.id, quantity=10,
        company_id=product.company_id, actor_id=1, unit_cost=5.0,
    )
    db.refresh(product)
    assert product.cost_price == 5.0
    # Réception sans coût : le WAC ne doit pas tomber à 0.
    repository.restock_product(
        db, product_id=product.id, branch_id=branch.id, quantity=10,
        company_id=product.company_id, actor_id=1, unit_cost=0.0,
    )
    db.refresh(product)
    assert product.cost_price == 5.0


def test_reorder_point_uses_demand_lead_and_safety(db, product):
    product.avg_daily_demand = 4.0
    product.lead_time_days = 5
    product.safety_stock = 10
    product.min_threshold = 0
    db.commit()
    db.refresh(product)
    # ROP = 4*5 + 10 = 30
    assert product.reorder_point == 30


def test_reorder_point_falls_back_to_min_threshold(db, product):
    product.avg_daily_demand = 0.0
    product.lead_time_days = 0
    product.safety_stock = 0
    product.min_threshold = 7
    db.commit()
    db.refresh(product)
    assert product.reorder_point == 7


def test_alerts_when_on_hand_below_rop(db, product, branch):
    import repository
    repository.restock_product(
        db, product_id=product.id, branch_id=branch.id, quantity=3,
        company_id=product.company_id, actor_id=1, unit_cost=1.0,
    )
    product.min_threshold = 5
    db.commit()
    alerts = stock.get_alerts(db, product.company_id)
    assert any(p.id == product.id for p in alerts)


def test_stock_value_at_cost_not_price(db, product, branch):
    import repository
    repository.restock_product(
        db, product_id=product.id, branch_id=branch.id, quantity=10,
        company_id=product.company_id, actor_id=1, unit_cost=3.0,
    )
    # Valorisation = 10 * cost(3.0) = 30, indépendamment du prix de vente (10.0).
    assert stock.stock_value_at_cost(db, product.company_id) == 30.0


def test_eoq_wilson_formula():
    # EOQ = sqrt(2*D*S/H) ; D=1000, S=10, H=2 -> sqrt(10000)=100
    assert stock.economic_order_quantity(1000, 10, 2) == 100.0
    assert stock.economic_order_quantity(0, 10, 2) is None
