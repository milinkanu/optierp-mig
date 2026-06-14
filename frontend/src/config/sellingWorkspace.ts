// Config for the Selling workspace page (ERPNext-style). Data, not code:
// the page renders its sidebar and "Reports & Masters" grid from these.
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

export const SELLING_SIDEBAR: WsNavGroup[] = [
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
      { label: "Customer Group", to: "/m/customer-group" },
      { label: "Address", to: "/m/address" },
      { label: "Contact", to: "/m/contact" },
      { label: "Territory", to: "/m/territory" },
      { label: "Campaign", to: "/m/campaign" },
      { label: "Sales Person", to: "/m/sales-person" },
      { label: "Sales Partner", to: "/m/sales-partner" },
      { label: "Monthly Distribution", to: "/m/monthly-distribution" },
      { label: "Terms Template", to: "/m/terms-template" },
      { label: "UTM Source", to: "/m/utm-source" },
    ],
  },
  {
    title: "Items & Pricing",
    items: [{ label: "Item", to: "/items" }],
  },
  {
    title: "Reports",
    items: [{ label: "Reports", to: "/reports" }],
  },
];

export const SELLING_CARDS: WsGroup[] = [
  {
    title: "Selling",
    links: [
      { label: "Customer", planned: true },
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
      { label: "Customer Group", to: "/m/customer-group" },
      { label: "Territory", to: "/m/territory" },
      { label: "Campaign", to: "/m/campaign" },
      { label: "Address", to: "/m/address" },
      { label: "Contact", to: "/m/contact" },
      { label: "Monthly Distribution", to: "/m/monthly-distribution" },
      { label: "Terms Template", to: "/m/terms-template" },
      { label: "UTM Source", to: "/m/utm-source" },
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
      { label: "Shipping Rule", planned: true },
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
];
