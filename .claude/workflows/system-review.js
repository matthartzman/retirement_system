/**
 * System Review — GitHub MCP command-limited, CI-excluded workflow.
 *
 * Runs in a Claude Code project linked to a GitHub repository. GitHub interactions are
 * limited to the approved command list. CI/GitHub Actions is intentionally excluded.
 *
 * Read commands used:
 * get_me, search_repositories, list_branches, get_commit, list_commits, search_commits,
 * search_code, get_file_contents, list_issues, search_issues, issue_read,
 * list_pull_requests, search_pull_requests, pull_request_read, list_releases,
 * get_latest_release, get_release_by_tag, list_tags, get_tag,
 * list_repository_collaborators, get_teams, get_team_members, run_secret_scanning.
 *
 * Prohibited GitHub write commands:
 * create_or_update_file, delete_file, create_pull_request, update_pull_request,
 * update_pull_request_branch, merge_pull_request, pull_request_review_write,
 * add_reply_to_pull_request_comment, add_comment_to_pending_review,
 * request_copilot_review, issue_write, add_issue_comment, sub_issue_write,
 * create_branch, push_files, fork_repository, create_repository.
 *
 * The final report is written only by the local project report adapter. If that adapter
 * uses create_or_update_file, it may create only the selected previously non-existing
 * report path after quality gates pass and must never overwrite.
 */

export default async function systemReviewWorkflow({ scope, date, outPath, depth }) {
  const config = {
    scope: scope || "the entire system",
    date,
    outPath,
    depth: depth === "deep" ? "deep" : "standard",
    models: { expert: "expert_reasoning", standard: "standard_reasoning", recon: "recon", synthesis: "synthesis" },
    githubPolicy: {
      mode: "read-only-except-final-report",
      ciExcluded: true,
      allowedReadCommands: [
        "get_me", "search_repositories", "list_branches", "get_commit", "list_commits",
        "search_commits", "search_code", "get_file_contents", "list_issues", "search_issues",
        "issue_read", "list_pull_requests", "search_pull_requests", "pull_request_read",
        "list_releases", "get_latest_release", "get_release_by_tag", "list_tags", "get_tag",
        "list_repository_collaborators", "get_teams", "get_team_members", "run_secret_scanning"
      ]
    }
  };

  const identity = await github.get_me({});
  const repository = await resolveLinkedRepository({ scope: config.scope, identity });
  const refContext = await resolveReviewRef(repository);
  const manifest = await buildManifest({ repository, refContext, config, identity });

  const recon = await runParallel([
    { name: "engine-architecture-calculations", model: config.models.recon },
    { name: "ui-workflows", model: config.models.recon },
    { name: "tests-docs-data-config", model: config.models.recon }
  ], { manifest, config });

  const systemMap = normalizeSystemMap(recon, manifest);
  const coverage = createCoverageMatrix(systemMap, manifest);
  const expertReviews = await runParallel(panelForDepth(config.depth), { manifest, systemMap, coverage, config });
  const findings = normalizeAndDeduplicateFindings(expertReviews).filter(notCiRelated);
  const verifiedFindings = await verifyFindings(findings, { manifest, systemMap, coverage, config });

  let report = await synthesizeReport({ manifest, systemMap, coverage, findings: verifiedFindings, config });
  report = removeCiContent(report);

  const plannerSignoff = await plannerSignOff({ report, model: config.models.synthesis });
  report = removeCiContent(applyPlannerChanges(report, plannerSignoff));

  if (plannerSignoff.materialChanges) {
    report = removeCiContent(await reverifyAndResynthesize({
      report, plannerSignoff, manifest, systemMap, coverage, config
    }));
  }

  await validateReportQualityGate(report);
  await writeFinalReportOnly({ outPath: config.outPath, report, overwrite: false });
  return completionSummary(report, plannerSignoff, config.outPath);
}

async function buildManifest({ repository, refContext, config, identity }) {
  const [githubContext, inventory, accessContext, securityContext] = await Promise.all([
    collectGitHubWorkContext({ repository, refContext, scope: config.scope }),
    buildRepositoryInventory({ repository, refContext, scope: config.scope }),
    collectAccessContext({ repository }),
    collectSecurityContext({ repository })
  ]);
  return {
    review_run: {
      date: config.date,
      scope: config.scope,
      depth: config.depth,
      repository: {
        provider: "github", owner: repository.owner, name: repository.name,
        default_branch: refContext.defaultBranch, reviewed_ref: refContext.ref,
        commit_sha: refContext.commitSha, pull_request_number: refContext.pullRequestNumber || null,
        authenticated_user: identity.login || identity.username || "unknown"
      },
      github_policy: config.githubPolicy,
      github_context: githubContext,
      access_context: accessContext,
      security_context: securityContext,
      inventories: inventory,
      explicit_exclusions: ["ci_and_github_actions"]
    }
  };
}

async function resolveLinkedRepository({ scope, identity }) {
  const linked = await getLinkedProjectRepository();
  if (linked?.owner && linked?.name) return linked;
  const candidates = await github.search_repositories({ query: `user:${identity.login || identity.username}`, per_page: 100 });
  const matches = selectRepositoriesMatchingProject(candidates, scope);
  if (matches.length !== 1) throw new Error("Unable to uniquely resolve the GitHub repository linked to this project.");
  return { owner: matches[0].owner.login, name: matches[0].name };
}

async function resolveReviewRef(repository) {
  const branches = await github.list_branches({ owner: repository.owner, repo: repository.name, per_page: 100 });
  const linkedRef = await getLinkedProjectRef();
  const defaultBranch = await inferDefaultBranch(repository, branches);
  const ref = linkedRef?.ref || defaultBranch;
  const commit = await github.get_commit({ owner: repository.owner, repo: repository.name, ref });
  const pullRequest = await findPullRequestForRef(repository, ref);
  return { defaultBranch, ref, commitSha: commit.sha, pullRequestNumber: pullRequest?.number || null };
}

async function collectGitHubWorkContext({ repository, refContext, scope }) {
  const common = { owner: repository.owner, repo: repository.name, per_page: 100 };
  const [openIssues, openPrs, recentCommits, tags, releases, latestRelease, scopedIssues, scopedPrs] = await Promise.all([
    github.list_issues({ ...common, state: "open" }), github.list_pull_requests({ ...common, state: "open" }),
    github.list_commits({ ...common, sha: refContext.ref }), github.list_tags(common), github.list_releases(common),
    github.get_latest_release(common).catch(() => null),
    github.search_issues({ q: `repo:${repository.owner}/${repository.name} is:issue is:open ${scope}` }),
    github.search_pull_requests({ query: `repo:${repository.owner}/${repository.name} is:pr ${scope}` })
  ]);
  const pullRequests = await hydratePullRequests({ repository, ref: refContext.ref, candidates: mergeUniqueByNumber(openPrs, scopedPrs) });
  const scopeRelatedCommits = await github.search_commits({ q: `repo:${repository.owner}/${repository.name} ${scope}` }).catch(() => []);
  return {
    access: "GitHub MCP", open_issues: selectRelevantWorkItems(openIssues, scopedIssues, scope),
    flagged_or_pending_issues: selectFlaggedOrPendingIssues(openIssues, scopedIssues), open_pull_requests: pullRequests,
    recent_commits: recentCommits.slice(0, 30), scope_related_commits: scopeRelatedCommits.slice(0, 30),
    tags: tags.slice(0, 30), releases: releases.slice(0, 10), latest_release: latestRelease
  };
}

async function buildRepositoryInventory({ repository, refContext, scope }) {
  const queries = ["path:documentation", "path:docs", "filename:README", "filename:ARCHITECTURE", "filename:DESIGN", "filename:IMPLEMENTATION", "filename:ADR", "path:.github", "filename:package.json", "filename:pyproject.toml", "filename:requirements.txt", "filename:Cargo.toml", "filename:go.mod", "filename:docker-compose.yml", "filename:compose.yml", "filename:Makefile", "filename:README.md"];
  const results = await Promise.all(queries.map(query => github.search_code({ q: `repo:${repository.owner}/${repository.name} ${query}` })));
  const candidates = flattenAndDedupeCodeSearch(results);
  // Throttled instead of a single 250-wide Promise.all: an unbounded burst of get_file_contents
  // calls risks GitHub secondary rate limits on larger repositories.
  const files = await mapWithConcurrency(candidates.slice(0, 250), FILE_FETCH_CONCURRENCY, async item => {
    const content = await github.get_file_contents({ owner: repository.owner, repo: repository.name, ref: refContext.ref, path: item.path });
    return { path: item.path, sha: content.sha, content: decodeGitHubContent(content) };
  });
  return classifyInventory(files, scope);
}

const FILE_FETCH_CONCURRENCY = 8;

/**
 * Runs `worker` over `items` with at most `limit` in flight at once, preserving input order
 * in the returned array. A plain Promise.all over hundreds of GitHub calls (e.g. the repository
 * inventory fetch) can trip secondary rate limits; this bounds the burst instead.
 */
async function mapWithConcurrency(items, limit, worker) {
  const results = new Array(items.length);
  let nextIndex = 0;
  async function runLane() {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex++;
      results[currentIndex] = await worker(items[currentIndex], currentIndex);
    }
  }
  const lanes = Array.from({ length: Math.min(limit, items.length) }, runLane);
  await Promise.all(lanes);
  return results;
}

async function hydratePullRequests({ repository, ref, candidates }) {
  const selected = candidates.filter(pr => pr.head?.ref === ref || pr.base?.ref === ref || isPotentiallyRelevant(pr)).slice(0, 30);
  return Promise.all(selected.map(pr => github.pull_request_read({ owner: repository.owner, repo: repository.name, pull_number: pr.number, method: "get" })));
}

async function findPullRequestForRef(repository, ref) {
  const prs = await github.list_pull_requests({ owner: repository.owner, repo: repository.name, state: "open", per_page: 100 });
  return prs.find(pr => pr.head?.ref === ref) || null;
}

async function collectAccessContext({ repository }) {
  const collaborators = await github.list_repository_collaborators({ owner: repository.owner, repo: repository.name, per_page: 100 }).catch(() => ({ status: "unavailable" }));
  const teams = await github.get_teams({ owner: repository.owner, repo: repository.name, per_page: 100 }).catch(() => ({ status: "unavailable" }));
  return { collaborators, teams, note: "Review access configuration only; do not modify it." };
}

async function collectSecurityContext({ repository }) {
  const secretScan = await github.run_secret_scanning({ owner: repository.owner, repo: repository.name }).catch(error => ({ status: "unavailable", reason: String(error) }));
  return { secret_scanning: secretScan };
}

function notCiRelated(finding) {
  // Scoped to category/title only. Stringifying the whole finding previously matched on
  // legitimate content elsewhere in the object (e.g. an evidence path like src/pipeline/calc.py),
  // silently dropping non-CI findings.
  const scoped = `${finding.category || ""} ${finding.title || ""}`;
  return !/(\bci\b|github actions|workflow run|workflow job|check run|pipeline)/i.test(scoped);
}
function removeCiContent(report) { return stripCiSectionsAndClaims(report, "CI was intentionally excluded from this review."); }
function panelForDepth(depth) { const expert="expert_reasoning", standard="standard_reasoning"; return [{name:"architect",model:expert},{name:"financial-planner",model:expert},{name:"usability-accessibility",model:depth==="deep"?expert:standard},{name:"documentation",model:depth==="deep"?expert:standard},{name:"quality",model:depth==="deep"?expert:standard}]; }

// Host/project adapters: getLinkedProjectRepository, getLinkedProjectRef, inferDefaultBranch,
// selectRepositoriesMatchingProject, selectRelevantWorkItems, selectFlaggedOrPendingIssues,
// mergeUniqueByNumber, flattenAndDedupeCodeSearch, decodeGitHubContent, classifyInventory,
// isPotentiallyRelevant, normalizeSystemMap, createCoverageMatrix, runParallel,
// normalizeAndDeduplicateFindings, verifyFindings, synthesizeReport, plannerSignOff,
// applyPlannerChanges, reverifyAndResynthesize, stripCiSectionsAndClaims,
// validateReportQualityGate, writeFinalReportOnly, completionSummary.
//
// The `github` object (github.get_me, github.search_repositories, etc.) is likewise a host-
// provided binding, not imported here. Signatures, return shapes, and required failure
// behavior for every adapter above are specified in
// ../skills/system-review/references/adapter-contract.md — implement against that doc, not
// against inferred usage in this file.