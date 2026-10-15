import datetime
import random
from typing import Tuple
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    inspect,
    select,
)
from sqlalchemy.orm import declarative_base, Session
from app.database.connection import get_readwrite_engine

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)  # Sensitive field for AST guard tests
    phone = Column(String(20), nullable=False)
    city = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    category = Column(String(50), nullable=False)
    price = Column(Float, nullable=False)
    cost = Column(Float, nullable=False)
    stock_quantity = Column(Integer, nullable=False)
    rating = Column(Float, default=4.5)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_date = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String(30), nullable=False)  # COMPLETED, PENDING, CANCELLED, REFUNDED
    total_amount = Column(Float, nullable=False)
    shipping_fee = Column(Float, default=0.0)
    payment_method = Column(String(30), nullable=False)  # CREDIT_CARD, MOMO, COD, BANK_TRANSFER


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    discount = Column(Float, default=0.0)


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1 to 5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


def seed_ecommerce_database(db_path: str = None, force_reseed: bool = False) -> Tuple[bool, int]:
    """
    Creates tables and seeds 2,000+ realistic E-commerce records.
    Returns (seeded_flag, total_rows_inserted).
    """
    engine = get_readwrite_engine(db_path)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Check if already seeded
        user_count = session.query(User).count()
        if user_count > 0 and not force_reseed:
            total_existing = (
                session.query(User).count()
                + session.query(Product).count()
                + session.query(Order).count()
                + session.query(OrderItem).count()
                + session.query(Review).count()
            )
            return False, total_existing

        if force_reseed:
            session.query(Review).delete()
            session.query(OrderItem).delete()
            session.query(Order).delete()
            session.query(Product).delete()
            session.query(User).delete()
            session.commit()

        random.seed(42)  # Deterministic generation
        base_date = datetime.datetime(2025, 1, 1)

        # 1. Seed Users (150 users)
        cities = ["Hanoi", "Ho Chi Minh City", "Da Nang", "Hai Phong", "Can Tho", "Nha Trang"]
        first_names = ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Phan", "Vu", "Dang", "Bui", "Do"]
        middle_names = ["Van", "Thi", "Minh", "Duc", "Quang", "Anh", "Thanh", "Hai"]
        last_names = ["Nam", "Linh", "Huyen", "Tuan", "Dat", "Khoa", "Trang", "Phong", "Mai", "Son"]

        users = []
        for i in range(1, 151):
            fn = random.choice(first_names)
            mn = random.choice(middle_names)
            ln = random.choice(last_names)
            full_name = f"{fn} {mn} {ln}"
            email = f"user_{i}_{fn.lower()}.{ln.lower()}@ecommerce.vn"
            phone = f"09{random.randint(10000000, 99999999)}"
            city = random.choice(cities)
            reg_date = base_date + datetime.timedelta(days=random.randint(0, 300))
            # Sensitive password hash for testing AST Guard
            pwd_hash = f"$2b$12$e8xYz9exampleSaltHashPassword{i:04d}abcdef"
            users.append(
                User(
                    id=i,
                    full_name=full_name,
                    email=email,
                    password_hash=pwd_hash,
                    phone=phone,
                    city=city,
                    created_at=reg_date,
                )
            )
        session.bulk_save_objects(users)
        session.commit()

        # 2. Seed Products (100 products)
        categories = {
            "Electronics": [
                ("iPhone 16 Pro Max", 1299.0, 950.0),
                ("Samsung Galaxy S24 Ultra", 1199.0, 880.0),
                ("MacBook Pro M4 14-inch", 1999.0, 1500.0),
                ("Dell XPS 15 Laptop", 1699.0, 1250.0),
                ("Sony WH-1000XM5 Headphones", 399.0, 260.0),
                ("Apple Watch Series 10", 429.0, 310.0),
                ("Logitech MX Master 3S Mouse", 99.0, 65.0),
                ("Keychron Q1 Pro Mechanical Keyboard", 189.0, 120.0),
                ("LG C4 55-inch OLED 4K TV", 1499.0, 1050.0),
                ("iPad Pro M4 11-inch", 999.0, 750.0),
            ],
            "Fashion": [
                ("Slim Fit Oxford Shirt", 45.0, 22.0),
                ("Selvedge Denim Jeans", 89.0, 40.0),
                ("Classic Trench Coat", 199.0, 90.0),
                ("Merino Wool Knit Sweater", 79.0, 35.0),
                ("Leather Chelsea Boots", 160.0, 80.0),
                ("Canvas Everyday Sneakers", 65.0, 28.0),
                ("Waterproof Sport Jacket", 120.0, 55.0),
            ],
            "Home & Kitchen": [
                ("Air Fryer XXL Digital", 149.0, 85.0),
                ("Espresso Coffee Maker Pro", 299.0, 180.0),
                ("Robot Vacuum Cleaner Ultra", 499.0, 320.0),
                ("Stainless Steel Cookware Set", 189.0, 95.0),
                ("Ergonomic Mesh Office Chair", 249.0, 140.0),
                ("Smart Humidifier 4L", 59.0, 30.0),
            ],
            "Beauty & Health": [
                ("Hydrating Hyaluronic Serum", 38.0, 15.0),
                ("Vitamin C Brightening Cream", 45.0, 18.0),
                ("Sonic Electric Toothbrush", 79.0, 42.0),
                ("Hair Dryer Ionic Professional", 129.0, 70.0),
            ],
            "Sports & Fitness": [
                ("Adjustable Dumbbell Set 24kg", 180.0, 110.0),
                ("Yoga Mat Non-slip Eco", 35.0, 14.0),
                ("Smart Fitness Tracker Band", 69.0, 38.0),
                ("Insulated Stainless Water Bottle 1L", 28.0, 11.0),
            ],
        }

        products = []
        prod_id = 1
        for cat_name, items in categories.items():
            for name, price, cost in items:
                products.append(
                    Product(
                        id=prod_id,
                        name=name,
                        category=cat_name,
                        price=price,
                        cost=cost,
                        stock_quantity=random.randint(15, 300),
                        rating=round(random.uniform(4.0, 5.0), 1),
                        created_at=base_date,
                    )
                )
                prod_id += 1

        # Duplicate to reach exactly 100 products with variations
        base_count = len(products)
        while prod_id <= 100:
            idx = (prod_id - base_count - 1) % base_count
            orig = products[idx]
            products.append(
                Product(
                    id=prod_id,
                    name=f"{orig.name} (Gen {prod_id % 3 + 2})",
                    category=orig.category,
                    price=round(orig.price * random.uniform(0.9, 1.2), 2),
                    cost=round(orig.cost * random.uniform(0.9, 1.15), 2),
                    stock_quantity=random.randint(20, 250),
                    rating=round(random.uniform(3.8, 5.0), 1),
                    created_at=base_date,
                )
            )
            prod_id += 1

        session.bulk_save_objects(products)
        session.commit()

        # 3. Seed Orders (500 orders) & Order Items (1,200+ order_items)
        statuses = ["COMPLETED", "COMPLETED", "COMPLETED", "PENDING", "CANCELLED", "REFUNDED"]
        payment_methods = ["CREDIT_CARD", "MOMO", "COD", "BANK_TRANSFER"]

        orders = []
        order_items = []
        item_id = 1

        for o_id in range(1, 501):
            user_id = random.randint(1, 150)
            order_date = base_date + datetime.timedelta(
                days=random.randint(10, 360), hours=random.randint(0, 23)
            )
            status = random.choice(statuses)
            pay_method = random.choice(payment_methods)
            shipping_fee = random.choice([0.0, 5.0, 10.0])

            # 1 to 4 items per order
            num_items = random.randint(1, 4)
            order_total = shipping_fee

            for _ in range(num_items):
                p = random.choice(products)
                qty = random.randint(1, 3)
                discount = random.choice([0.0, 0.0, 0.05, 0.1])
                effective_price = round(p.price * (1 - discount), 2)
                item_total = effective_price * qty
                order_total += item_total

                order_items.append(
                    OrderItem(
                        id=item_id,
                        order_id=o_id,
                        product_id=p.id,
                        quantity=qty,
                        unit_price=p.price,
                        discount=discount,
                    )
                )
                item_id += 1

            orders.append(
                Order(
                    id=o_id,
                    user_id=user_id,
                    order_date=order_date,
                    status=status,
                    total_amount=round(order_total, 2),
                    shipping_fee=shipping_fee,
                    payment_method=pay_method,
                )
            )

        session.bulk_save_objects(orders)
        session.bulk_save_objects(order_items)
        session.commit()

        # 4. Seed Reviews (350 reviews)
        comments = [
            "Excellent product, exceeded expectations!",
            "Great value for money, fast delivery.",
            "Quality is decent, but shipping took a while.",
            "Works as described, very satisfied with build quality.",
            "Would recommend to friends and family.",
            "Good packaging, pristine condition.",
            "Average quality, could be improved slightly.",
            "Top tier customer support and stellar product!",
        ]

        reviews = []
        for r_id in range(1, 351):
            u_id = random.randint(1, 150)
            p_id = random.randint(1, 100)
            rating = random.choices([5, 4, 3, 2, 1], weights=[50, 30, 10, 5, 5])[0]
            comment = random.choice(comments)
            rev_date = base_date + datetime.timedelta(days=random.randint(30, 365))
            reviews.append(
                Review(
                    id=r_id,
                    user_id=u_id,
                    product_id=p_id,
                    rating=rating,
                    comment=comment,
                    created_at=rev_date,
                )
            )

        session.bulk_save_objects(reviews)
        session.commit()

        total_seeded = len(users) + len(products) + len(orders) + len(order_items) + len(reviews)
        return True, total_seeded
