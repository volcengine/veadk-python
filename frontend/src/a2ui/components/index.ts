// Auto-register every component directory.
//
// Each `components/<Name>/index.ts` calls `register("<Name>", renderer)`. This
// glob imports them all eagerly, so adding a new enterprise component is just a
// matter of dropping a new folder here (plus a matching backend catalog entry).
const modules = import.meta.glob("./*/index.ts", { eager: true });
void modules;
