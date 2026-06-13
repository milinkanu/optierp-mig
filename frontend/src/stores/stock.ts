// Module 03 — Stock Pinia store: items, warehouses, item groups, price lists.

import { defineStore } from "pinia";
import { api } from "@/api/client";
import type { ListResponse } from "@/types/core";
import type { Item, ItemGroup, ItemListItem, ItemRate, PriceList, Warehouse } from "@/types/stock";

interface StockState {
  items: ItemListItem[];
  warehouses: Warehouse[];
  itemGroups: ItemGroup[];
  priceLists: PriceList[];
}

export const useStockStore = defineStore("stock", {
  state: (): StockState => ({
    items: [],
    warehouses: [],
    itemGroups: [],
    priceLists: [],
  }),
  getters: {
    leafWarehouses: (state) => state.warehouses.filter((w) => !w.is_group && !w.disabled),
    itemOptions: (state) =>
      state.items
        .filter((i) => !i.disabled)
        .map((i) => ({ value: i.id, label: `${i.item_code} — ${i.item_name}` })),
  },
  actions: {
    async fetchItems(): Promise<void> {
      const resp = await api.get<ListResponse<ItemListItem>>("/items", {
        params: { page_size: 200 },
      });
      this.items = resp.data.items;
    },
    async fetchWarehouses(): Promise<void> {
      const resp = await api.get<Warehouse[]>("/warehouses");
      this.warehouses = resp.data;
    },
    async fetchItemGroups(): Promise<void> {
      const resp = await api.get<ItemGroup[]>("/item-groups");
      this.itemGroups = resp.data;
    },
    async fetchPriceLists(): Promise<void> {
      const resp = await api.get<PriceList[]>("/price-lists");
      this.priceLists = resp.data;
    },
    async createItem(payload: Record<string, unknown>): Promise<Item> {
      const resp = await api.post<Item>("/items", payload);
      await this.fetchItems();
      return resp.data;
    },
    async createWarehouse(name: string): Promise<Warehouse> {
      const resp = await api.post<Warehouse>("/warehouses", { warehouse_name: name });
      await this.fetchWarehouses();
      return resp.data;
    },
    async resolveItemRate(itemId: string, buying: boolean): Promise<ItemRate> {
      const resp = await api.get<ItemRate>(`/items/${itemId}/rate`, { params: { buying } });
      return resp.data;
    },
  },
});
