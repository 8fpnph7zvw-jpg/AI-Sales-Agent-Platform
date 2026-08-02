"""Add enterprise sales ownership, scoring, RBAC, and connector deduplication.

Revision ID: 20260802_0008
Revises: 20260730_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "20260802_0008"
down_revision: str | None = "20260730_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sales_profiles",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("sales_name", sa.String(120), nullable=False),
        sa.Column("feishu_open_id", sa.String(128)),
        sa.Column(
            "created_time",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="user_id"),
        sa.UniqueConstraint("tenant_id", "feishu_open_id", name="tenant_feishu_open_id"),
    )
    op.create_index("ix_sales_profiles_tenant_name", "sales_profiles", ["tenant_id", "sales_name"])
    op.create_table(
        "customer_scores",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("tenant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("customer_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("score", mysql.TINYINT(unsigned=True), nullable=False),
        sa.Column("level", sa.String(1), nullable=False),
        sa.Column("need_follow", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_time",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        sa.CheckConstraint("level IN ('A','B','C','D')", name="level_allowed"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_scores_customer_created",
        "customer_scores",
        ["customer_id", "created_time"],
    )
    op.create_index(
        "ix_customer_scores_tenant_follow",
        "customer_scores",
        ["tenant_id", "need_follow", "created_time"],
    )
    op.execute(
        sa.text(
            """INSERT INTO permissions (code, resource, action, description)
            VALUES ('customer.score_read','customer','score_read',
                    'View customer scoring results') AS new
            ON DUPLICATE KEY UPDATE description = new.description"""
        )
    )
    op.execute(
        sa.text(
            """INSERT INTO roles
            (public_id, tenant_id, code, name, description, is_system)
            SELECT LEFT(REPLACE(UUID(),'-',''),26), t.id, 'admin',
                   'Administrator', 'Administrator with full tenant access.', 1
            FROM tenants t WHERE NOT EXISTS
            (SELECT 1 FROM roles r WHERE r.tenant_id=t.id AND r.code='admin')"""
        )
    )
    op.execute(
        sa.text(
            """INSERT IGNORE INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
            WHERE r.code='admin'"""
        )
    )
    op.execute(
        sa.text(
            """INSERT IGNORE INTO user_roles (user_id, role_id, assigned_by)
            SELECT ur.user_id, admin_role.id, ur.assigned_by
            FROM user_roles ur
            JOIN roles old_role ON old_role.id=ur.role_id AND old_role.code='owner'
            JOIN roles admin_role ON admin_role.tenant_id=old_role.tenant_id
                 AND admin_role.code='admin'"""
        )
    )
    op.execute(sa.text("DELETE r FROM roles r WHERE r.code='owner' AND r.is_system=1"))
    op.execute(
        sa.text(
            """INSERT INTO roles
            (public_id, tenant_id, code, name, description, is_system)
            SELECT LEFT(REPLACE(UUID(),'-',''),26), t.id, 'sales', 'Sales',
                   'Sales users restricted to their own business data.', 1
            FROM tenants t WHERE NOT EXISTS
            (SELECT 1 FROM roles r WHERE r.tenant_id=t.id AND r.code='sales')"""
        )
    )
    op.execute(
        sa.text(
            """INSERT IGNORE INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code IN
            ('dashboard.read','customer.read_own','customer.create',
             'customer.update_own','conversation.read_own','message.send',
             'product.read','quotation.read_own','quotation.create',
             'quotation.update_own','customer.score_read')
            WHERE r.code='sales'"""
        )
    )

    # Preserve the most useful WhatsApp row and hide stale/demo duplicates without
    # deleting records referenced by conversations and webhook logs.
    op.execute(
        sa.text(
            """CREATE TEMPORARY TABLE connector_duplicates AS
            SELECT id FROM (
              SELECT id, ROW_NUMBER() OVER (
                PARTITION BY tenant_id ORDER BY (deleted_at IS NULL) DESC,
                (external_account_id <> 'demo-template') DESC,
                (status = 'active') DESC, (last_connected_at IS NOT NULL) DESC,
                last_connected_at DESC, id DESC) AS row_no
              FROM connectors WHERE provider = 'whatsapp'
            ) ranked WHERE row_no > 1"""
        )
    )
    op.execute(
        sa.text(
            """UPDATE connectors
            SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP(6))
            WHERE id IN (SELECT id FROM connector_duplicates)"""
        )
    )
    op.execute(sa.text("DROP TEMPORARY TABLE connector_duplicates"))


def downgrade() -> None:
    op.drop_index("ix_customer_scores_tenant_follow", table_name="customer_scores")
    op.drop_index("ix_customer_scores_customer_created", table_name="customer_scores")
    op.drop_table("customer_scores")
    op.drop_index("ix_sales_profiles_tenant_name", table_name="sales_profiles")
    op.drop_table("sales_profiles")
