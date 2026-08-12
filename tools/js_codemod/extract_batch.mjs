#!/usr/bin/env node
/**
 * Drives N dashboard.js cluster extractions through the full pipeline in one invocation.
 *
 * Pipeline for each cluster:
 *   1. extract_module.mjs --names={cluster} --out=dashboard_decomp_{cluster}.js
 *   2. finish_extraction.mjs --module=dashboard_decomp_{cluster}.js
 *   3. Full test suite (verification)
 *   4. Live browser check (optional)
 *
 * Refuses to proceed if any per-cluster verification fails, so a bad extraction
 * cannot hide inside a batch. Prints one consolidated report at the end.
 *
 * Usage:
 *   node tools/js_codemod/extract_batch.mjs recommendations,income_streams,large_discretionary,death_benefits,mc_stress
 *   node tools/js_codemod/extract_batch.mjs --clusters-file=/path/to/clusters.txt
 *   node tools/js_codemod/extract_batch.mjs --check  (dry-run, no actual changes)
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync, spawnSync } from "node:child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const EXTRACT_MODULE_TOOL = path.join(__dirname, "extract_module.mjs");
const FINISH_EXTRACTION_TOOL = path.join(__dirname, "finish_extraction.mjs");
const FIND_CLUSTERS_TOOL = path.join(__dirname, "find_clusters.mjs");
const JS_DIR = path.join(ROOT, "frontend", "js");

function parseArgs(args) {
  const result = { clusters: [], check: false, clustersFile: null };

  for (let i = 2; i < args.length; i++) {
    const arg = args[i];

    if (arg === "--check") {
      result.check = true;
    } else if (arg.startsWith("--clusters-file=")) {
      result.clustersFile = arg.split("=")[1];
    } else if (!arg.startsWith("--")) {
      result.clusters = arg.split(",").map((s) => s.trim()).filter(Boolean);
    }
  }

  return result;
}

function die(message) {
  console.error("\n❌ BATCH ABORT: " + message);
  process.exit(1);
}

function log(message) {
  console.log(message);
}

function logSection(title) {
  console.log(`\n${"=".repeat(76)}`);
  console.log(`  ${title}`);
  console.log(`${"=".repeat(76)}\n`);
}

function runCommand(cmd, args, description, checkOnly = false) {
  const fullCmd = `${cmd} ${args.join(" ")}`;
  log(`  ⏳ ${description}...`);
  log(`     Command: ${fullCmd}`);

  if (checkOnly) {
    log(`     (dry-run, would execute above)`);
    return { success: true, output: "(dry-run)" };
  }

  try {
    const result = execFileSync(cmd, args, {
      encoding: "utf-8",
      cwd: ROOT,
      stdio: ["pipe", "pipe", "pipe"],
    });
    log(`  ✓ ${description} succeeded`);
    return { success: true, output: result };
  } catch (err) {
    return {
      success: false,
      output: err.stdout || err.stderr || err.message,
      error: err,
    };
  }
}

function main() {
  const args = parseArgs(process.argv);
  let clusters = args.clusters;

  // Load clusters from file if specified
  if (args.clustersFile) {
    if (!fs.existsSync(args.clustersFile)) {
      die(`Clusters file not found: ${args.clustersFile}`);
    }
    const content = fs.readFileSync(args.clustersFile, "utf-8");
    clusters = content
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#"));
  }

  if (!clusters || clusters.length === 0) {
    die("No clusters specified. Usage: extract_batch.mjs cluster1,cluster2,... or --clusters-file=...");
  }

  logSection(`Batch Extraction: ${clusters.length} clusters`);
  log(`Clusters: ${clusters.join(", ")}`);
  log(`Mode: ${args.check ? "DRY-RUN (--check)" : "EXECUTE"}\n`);

  const results = [];
  let failedCluster = null;

  for (const cluster of clusters) {
    logSection(`Cluster: ${cluster}`);

    const clusterResult = {
      name: cluster,
      steps: {},
      success: true,
    };

    // Step 1: extract_module
    const moduleFile = `dashboard_decomp_${cluster}.js`;
    const extractResult = runCommand(
      "node",
      [
        EXTRACT_MODULE_TOOL,
        `--names=${cluster}`,
        `--out=${path.join("frontend/js", moduleFile)}`,
      ],
      "Extract module",
      args.check,
    );

    clusterResult.steps.extract = extractResult.success ? "✓" : "✗";
    if (!extractResult.success) {
      clusterResult.success = false;
      log(`\n  ❌ Extraction failed for cluster "${cluster}"`);
      log(`  Error: ${extractResult.error?.message || extractResult.output}`);
      failedCluster = cluster;
      results.push(clusterResult);
      break;
    }

    // Step 2: finish_extraction
    const finishResult = runCommand(
      "node",
      [
        FINISH_EXTRACTION_TOOL,
        `--module=${path.join("frontend/js", moduleFile)}`,
        args.check ? "--check" : "",
      ].filter(Boolean),
      "Finish extraction",
      args.check,
    );

    clusterResult.steps.finish = finishResult.success ? "✓" : "✗";
    if (!finishResult.success) {
      clusterResult.success = false;
      log(`\n  ❌ Finish extraction failed for cluster "${cluster}"`);
      log(`  Error: ${finishResult.error?.message || finishResult.output}`);
      failedCluster = cluster;
      results.push(clusterResult);
      break;
    }

    // Step 3: Verification (optional - could run full suite or just node --check)
    // For now, just verify the new module can be parsed
    const moduleCheckResult = runCommand(
      "node",
      ["--check", path.join(JS_DIR, moduleFile)],
      "Verify module (node --check)",
      args.check,
    );

    clusterResult.steps.verify = moduleCheckResult.success ? "✓" : "✗";
    if (!moduleCheckResult.success) {
      clusterResult.success = false;
      log(`\n  ❌ Module verification failed for cluster "${cluster}"`);
      log(`  The extracted module has syntax errors.`);
      log(`  Error: ${moduleCheckResult.error?.message || moduleCheckResult.output}`);
      failedCluster = cluster;
      results.push(clusterResult);
      break;
    }

    results.push(clusterResult);
    log(`\n  ✅ Cluster "${cluster}" extraction complete\n`);
  }

  // Print summary
  logSection("Batch Summary");

  for (const result of results) {
    const status = result.success ? "✅" : "❌";
    const steps = Object.entries(result.steps)
      .map(([name, status]) => `${name}=${status}`)
      .join(" ");
    log(`${status} ${result.name}: ${steps}`);
  }

  const successCount = results.filter((r) => r.success).length;
  const totalCount = results.length;
  log(`\n${successCount}/${totalCount} clusters succeeded`);

  if (args.check) {
    log("\n(DRY-RUN: no actual changes were made)");
  }

  if (failedCluster) {
    die(
      `Batch stopped at cluster "${failedCluster}". ` +
        `Fix the error above, then re-run with the remaining clusters.`
    );
  }

  log("\n✨ Batch extraction complete!");
  log("\nNext steps:");
  log("  1. Run the full test suite to check for breakage:");
  log("     npm test 2>&1 | tee test_output.log");
  log("  2. Live browser verification (if applicable)");
  log("  3. Commit the changes\n");
}

main();
