// Config for module workspace pages (ERPNext-style), shared by ModuleWorkspace.vue.
// Data, not code: each module defines its sidebar + "Reports & Masters" grid here.
// `to` is a router path; links without `to` (planned:true) render greyed.

export interface WsLink {
  label: string;
  to?: string;
  planned?: boolean;
}

export interface WsGroup {
  title: string;
  links: WsLink[];
}

export interface WsNavItem {
  label: string;
  to: string;
  icon?: string;
}

export interface WsNavGroup {
  title?: string;
  items: WsNavItem[];
}

export interface WorkspaceConfig {
  key: string;
  title: string;
  statsEndpoint: string;
  sidebar: WsNavGroup[];
  cards: WsGroup[];
}

const SELLING: WorkspaceConfig = {
  key: "selling",
  title: "Selling",
  statsEndpoint: "/selling/workspace",
  sidebar: [
    {
      items: [
        { label: "Home", to: "/", icon: "⌂" },
        { label: "Dashboard", to: "/selling", icon: "▦" },
        { label: "Quotation", to: "/quotations", icon: "📝" },
        { label: "Sales Order", to: "/sales-orders", icon: "🛒" },
        { label: "Sales Invoice", to: "/sales-invoices", icon: "🧾" },
        { label: "Delivery Note", to: "/delivery-notes", icon: "🚚" },
      ],
    },
    {
      title: "Setup",
      items: [
        { label: "Customer", to: "/m/customer" },
        { label: "Address", to: "/m/address" },
        { label: "Campaign", to: "/m/campaign" },
        { label: "Contact", to: "/m/contact" },
        { label: "Customer Group", to: "/m/customer-group" },
        { label: "Monthly Distribution", to: "/m/monthly-distribution" },
        { label: "Sales Partner", to: "/m/sales-partner" },
        { label: "Sales Person", to: "/m/sales-person" },
        { label: "Territory", to: "/m/territory" },
        { label: "Terms Template", to: "/m/terms-template" },
        { label: "UTM Source", to: "/m/utm-source" },
      ],
    },
    {
      title: "Items & Pricing",
      items: [
        { label: "Item", to: "/items" },
        { label: "Pricing Rule", to: "/m/pricing-rule" },
      ],
    },
    { title: "Reports", items: [{ label: "Reports", to: "/reports" }] },
  ],
  cards: [
    {
      title: "Selling",
      links: [
        { label: "Customer", to: "/m/customer" },
        { label: "Quotation", to: "/quotations" },
        { label: "Sales Order", to: "/sales-orders" },
        { label: "Sales Invoice", to: "/sales-invoices" },
        { label: "Delivery Note", to: "/delivery-notes" },
        { label: "Sales Partner", to: "/m/sales-partner" },
        { label: "Sales Person", to: "/m/sales-person" },
      ],
    },
    {
      title: "Setup",
      links: [
        { label: "Address", to: "/m/address" },
        { label: "Campaign", to: "/m/campaign" },
        { label: "Contact", to: "/m/contact" },
        { label: "Customer Group", to: "/m/customer-group" },
        { label: "Monthly Distribution", to: "/m/monthly-distribution" },
        { label: "Territory", to: "/m/territory" },
        { label: "Terms Template", to: "/m/terms-template" },
        { label: "UTM Source", to: "/m/utm-source" },
      ],
    },
    {
      title: "Items & Pricing",
      links: [
        { label: "Item", to: "/items" },
        { label: "Pricing Rule", to: "/m/pricing-rule" },
        { label: "Coupon Code", to: "/m/coupon-code" },
        { label: "Item Group", planned: true },
        { label: "Price List", planned: true },
        { label: "Item Price", planned: true },
        { label: "Shipping Rule", to: "/m/shipping-rule" },
        { label: "Product Bundle", to: "/m/product-bundle" },
      ],
    },
    {
      title: "Settings",
      links: [
        { label: "Tax Template", planned: true },
        { label: "Terms Template", to: "/m/terms-template" },
        { label: "Selling Settings", to: "/settings" },
      ],
    },
    {
      title: "Key Reports",
      links: [
        { label: "Financial Reports", to: "/reports" },
        { label: "Stock Balance", to: "/stock-balance" },
      ],
    },
    {
      title: "Point of Sale",
      links: [
        { label: "POS Profile", planned: true },
        { label: "POS Invoice", planned: true },
        { label: "Loyalty Program", planned: true },
      ],
    },
  ],
};

const BUYING: WorkspaceConfig = {
  key: "buying",
  title: "Buying",
  statsEndpoint: "/buying/workspace",
  sidebar: [
    {
      items: [
        { label: "Home", to: "/", icon: "⌂" },
        { label: "Dashboard", to: "/buying", icon: "▦" },
        { label: "Material Request", to: "/material-requests", icon: "📋" },
        { label: "Request for Quotation", to: "/sourcing", icon: "📨" },
        { label: "Purchase Order", to: "/purchase-orders", icon: "🛍" },
        { label: "Purchase Receipt", to: "/purchase-receipts", icon: "📦" },
        { label: "Purchase Invoice", to: "/purchase-invoices", icon: "📥" },
      ],
    },
    {
      title: "Setup",
      items: [
        { label: "Address", to: "/m/address" },
        { label: "Contact", to: "/m/contact" },
        { label: "Terms Template", to: "/m/terms-template" },
        { label: "Item", to: "/items" },
      ],
    },
    { title: "Reports", items: [{ label: "Reports", to: "/reports" }] },
  ],
  cards: [
    {
      title: "Buying",
      links: [
        { label: "Supplier", planned: true },
        { label: "Material Request", to: "/material-requests" },
        { label: "Request for Quotation", to: "/sourcing" },
        { label: "Supplier Quotation", to: "/sourcing" },
        { label: "Purchase Order", to: "/purchase-orders" },
        { label: "Purchase Receipt", to: "/purchase-receipts" },
        { label: "Purchase Invoice", to: "/purchase-invoices" },
      ],
    },
    {
      title: "Setup",
      links: [
        { label: "Supplier", planned: true },
        { label: "Supplier Group", planned: true },
        { label: "Address", to: "/m/address" },
        { label: "Contact", to: "/m/contact" },
        { label: "Terms Template", to: "/m/terms-template" },
      ],
    },
    {
      title: "Items & Pricing",
      links: [
        { label: "Item", to: "/items" },
        { label: "Item Group", planned: true },
        { label: "Price List", planned: true },
        { label: "Item Price", planned: true },
        { label: "Pricing Rule", planned: true },
        { label: "Product Bundle", planned: true },
      ],
    },
    {
      title: "Settings",
      links: [
        { label: "Tax Template", planned: true },
        { label: "Terms Template", to: "/m/terms-template" },
        { label: "Buying Settings", to: "/settings" },
      ],
    },
    {
      title: "Key Reports",
      links: [
        { label: "Financial Reports", to: "/reports" },
        { label: "Stock Balance", to: "/stock-balance" },
      ],
    },
  ],
};

const STOCK: WorkspaceConfig = {
  key: "stock",
  title: "Stock",
  statsEndpoint: "/stock/workspace",
  sidebar: [
    {
      items: [
        { label: "Home", to: "/", icon: "⌂" },
        { label: "Dashboard", to: "/stock", icon: "▦" },
        { label: "Item", to: "/items", icon: "🏷" },
        { label: "Warehouse", to: "/warehouses", icon: "🏬" },
        { label: "Stock Entry", to: "/stock-entries", icon: "↔" },
        { label: "Material Request", to: "/material-requests", icon: "📋" },
        { label: "Stock Balance", to: "/stock-balance", icon: "📈" },
        { label: "Purchase Receipt", to: "/purchase-receipts", icon: "📦" },
        { label: "Delivery Note", to: "/delivery-notes", icon: "🚚" },
      ],
    },
    { title: "Reports", items: [{ label: "Reports", to: "/reports" }] },
  ],
  cards: [
    {
      title: "Stock Transactions",
      links: [
        { label: "Stock Entry", to: "/stock-entries" },
        { label: "Material Request", to: "/material-requests" },
        { label: "Purchase Receipt", to: "/purchase-receipts" },
        { label: "Delivery Note", to: "/delivery-notes" },
        { label: "Stock Balance", to: "/stock-balance" },
      ],
    },
    {
      title: "Items & Pricing",
      links: [
        { label: "Item", to: "/items" },
        { label: "Item Group", planned: true },
        { label: "Price List", planned: true },
        { label: "Item Price", planned: true },
        { label: "Product Bundle", planned: true },
      ],
    },
    {
      title: "Setup",
      links: [
        { label: "Warehouse", to: "/warehouses" },
        { label: "Item Group", planned: true },
        { label: "UOM", planned: true },
        { label: "Brand", planned: true },
      ],
    },
    {
      title: "Key Reports",
      links: [
        { label: "Stock Balance", to: "/stock-balance" },
        { label: "Financial Reports", to: "/reports" },
      ],
    },
  ],
};

const ACCOUNTING: WorkspaceConfig = {
  key: "accounting",
  title: "Accounting",
  statsEndpoint: "/accounting/workspace",
  sidebar: [
    {
      items: [
        { label: "Home", to: "/", icon: "⌂" },
        { label: "Dashboard", to: "/accounting", icon: "▦" },
        { label: "Sales Invoice", to: "/sales-invoices", icon: "🧾" },
        { label: "Purchase Invoice", to: "/purchase-invoices", icon: "📥" },
        { label: "Journal Entry", to: "/journal-entries", icon: "📒" },
        { label: "Payment Entry", to: "/payment-entries", icon: "💸" },
      ],
    },
    {
      title: "Setup",
      items: [
        { label: "Reconciliation", to: "/payment-reconciliation" },
        { label: "Budget", to: "/budgets" },
        { label: "Terms Template", to: "/m/terms-template" },
      ],
    },
    { title: "Reports", items: [{ label: "Reports", to: "/reports" }] },
  ],
  cards: [
    {
      title: "Transactions",
      links: [
        { label: "Sales Invoice", to: "/sales-invoices" },
        { label: "Purchase Invoice", to: "/purchase-invoices" },
        { label: "Journal Entry", to: "/journal-entries" },
        { label: "Payment Entry", to: "/payment-entries" },
      ],
    },
    {
      title: "Banking & Reconciliation",
      links: [
        { label: "Payment Reconciliation", to: "/payment-reconciliation" },
        { label: "Bank Reconciliation", planned: true },
      ],
    },
    {
      title: "Setup",
      links: [
        { label: "Budget", to: "/budgets" },
        { label: "Terms Template", to: "/m/terms-template" },
        { label: "Chart of Accounts", planned: true },
        { label: "Tax Template", planned: true },
        { label: "Tax Category", planned: true },
      ],
    },
    {
      title: "Key Reports",
      links: [{ label: "Financial Reports", to: "/reports" }],
    },
  ],
};

export const WORKSPACES: Record<string, WorkspaceConfig> = {
  selling: SELLING,
  buying: BUYING,
  stock: STOCK,
  accounting: ACCOUNTING,
};
