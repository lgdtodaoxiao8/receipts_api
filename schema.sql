DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS receipts;


CREATE TABLE receipts (
    id SERIAL PRIMARY KEY,
    purchased_at TIMESTAMPTZ NOT NULL,
    total NUMERIC(10,2),
    shop TEXT
);

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE items (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    price NUMERIC(10,2) NOT NULL,
    receipt_id INTEGER NOT NULL REFERENCES receipts(id),
    category_id INTEGER REFERENCES categories(id)
);

CREATE INDEX idx_items_receipt_id ON items (receipt_id);
CREATE INDEX idx_items_category_id ON items (category_id);