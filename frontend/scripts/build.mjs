import { spawnSync } from "node:child_process";

const executable = (name) => process.platform === "win32" ? `${name}.cmd` : name;

function run(command, args) {
  const result = spawnSync(executable(command), args, {
    cwd: process.cwd(),
    env: process.env,
    stdio: "inherit",
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const viteArgs = process.argv.slice(2);

run("tsc", []);
run("vite", ["build", ...viteArgs]);
run("vite", [
  "build",
  "--config",
  "vite.website-integration.config.ts",
  ...viteArgs,
]);
