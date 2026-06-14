// Types for the metadata engine ("the machine"): the /meta/{doctype} contract
// that drives the generic list and form views.

import type { FieldConfig } from "@/components/shared/FormBuilder.vue";

export interface MetaColumn {
  key: string;
  label: string;
}

export interface DocTypeMeta {
  name: string;
  slug: string;
  title_field: string;
  naming: string;
  scoped: boolean;
  is_tree: boolean;
  parent_field: string | null;
  group: string;
  fields: FieldConfig[];
  list_fields: MetaColumn[];
}
