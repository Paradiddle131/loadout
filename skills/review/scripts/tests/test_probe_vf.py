import pytest
from test_review_scripts import World, env, w  # noqa: F401
F = "```"
G = "### CLM-1\n- rank: must-fix\n- claim: x\n- harm: an operator merges a broken gate\n"
# name: (text, expected: "post" or "refuse")
CASES = {
 "A_backtick_rank_no_harm": ("## Must-fix\n" + G + "### COR-2\n- rank: `must-fix`\n- claim: wrong total\n", "refuse"),
 "B_bold_rank_no_harm": ("## Must-fix\n" + G + "### COR-2\n- rank: **must-fix**\n- claim: wrong total\n", "refuse"),
 "C_only_backtick_rank_with_harm": ("## Must-fix\n### COR-2\n- rank: `must-fix`\n- claim: x\n- harm: a reader trusts a wrong total\n", "post"),
 "D_unclosed_fence_hides_next": ("## Must-fix\n" + G + "- evidence: sed -n 3p a.md ->\n```bash\n### COR-2\n- rank: must-fix\n- claim: wrong total\n", "refuse"),
 "E_unclosed_fence_before_harm": ("## Must-fix\n### CLM-1\n- rank: must-fix\n- claim: x\n- evidence: sed -n 12p README.md ->\n```bash\n- harm: an operator merges a broken gate\n", "post"),
 "F_stray_fence_in_preamble": ("Lens heads: x\nnote: sed -n 41p agents/finding-verifier.md ->\n```\n## Must-fix\n" + G, "post"),
 "G_heredoc_fence_hides_next": ("## Must-fix\n" + G + "- reproduce: cat > f.md <<'MD'\n```\n### X\nMD\n### COR-2\n- rank: must-fix\n- claim: wording only\n", "refuse"),
 "H_backtick_h3_merges_into_previous": ("## Must-fix\n" + G + "### `COR-2`\n- rank: must-fix\n- claim: wrong total\n", "refuse"),
 "I_bold_h3_alone_with_harm": ("## Must-fix\n### **COR-2**\n- rank: must-fix\n- harm: a reader trusts a wrong total\n", "post"),
 "J_quoted_rank_nit": ("## Must-fix\n" + G + "### COR-2\n- rank: must-fix\n- claim: wrong\n- evidence: sed -n 4p t.md ->\n- rank: nit\n", "refuse"),
 "K_quoted_harm_none_blanks_harm": ("## Must-fix\n### COR-2\n- rank: must-fix\n- harm: a reader trusts a wrong total\n- evidence: grep harm out.md ->\n- harm: none\n", "post"),
 "L_quoted_harm_supplies_missing": ("## Must-fix\n### COR-2\n- rank: must-fix\n- claim: x\n- evidence: sed -n 55p agents/finding-verifier.md ->\n- harm: <must-fix only: who acts wrongly>\n", "refuse"),
 "M_bold_label_colon_outside": ("## Must-fix\n### COR-2\n- **rank**: must-fix\n- **harm**: a reader trusts a wrong total\n", "post"),
 "N_whole_output_fenced": (F + "text\n## Must-fix\n### CLM-1\n- rank: must-fix\n- harm: an operator trusts a wrong total\n" + F + "\n", "post"),
 "O_each_block_fenced": ("## Must-fix\n" + F + "\n### CLM-1\n- rank: must-fix\n- harm: an operator trusts a wrong total\n" + F + "\n", "post"),
 "P_quoted_nits_heading_unranked": ("## Must-fix\n" + G + "- evidence: sed -n 50,53p agents/finding-verifier.md ->\n## Nits\n### COR-2\n- claim: wrong total\n", "refuse"),
 "Q_heredoc_idshaped_h3": ("## Must-fix\n### CTL-1\n- rank: must-fix\n- claim: x\n- harm: a lead posts a record that blocks on wording\n- reproduce: cat > out.md <<EOF\n### COR-9\n- rank: must-fix\n- claim: x\nEOF\n", "post"),
 "R_quoted_not_checked_before_harm": ("## Must-fix\n### COR-1\n- rank: must-fix\n- claim: x\n- evidence: sed -n 61p agents/finding-verifier.md ->\n## Not checked\n- harm: an operator trusts a wrong total\n", "post"),
 "S_settled_bullet_only": ("## Must-fix\nnone\n## Settled, not kept\n- COR-1 (must-fix): the fixed one still reproduces; harm: a lead merges a check that passes nothing.\n", "post"),
 "T_template_placeholder_harm": ("## Must-fix\n### CLM-1\n- rank: must-fix\n- claim: x\n- harm: <must-fix only: who acts wrongly or what breaks once this lands, and the cost; left out of a nit or pre-existing finding>\n", "refuse"),
 "U_paren_none_harm": ("## Must-fix\n### COR-2\n- rank: must-fix\n- harm: (none)\n", "refuse"),
 "V_control_good": ("## Must-fix\n" + G + "## Nits\n### CLM-3\n- rank: nit\n- claim: y\n", "post"),
 "W_control_no_harm": ("## Must-fix\n### COR-2\n- rank: must-fix\n- claim: y\n", "refuse"),
}
@pytest.mark.parametrize("name", list(CASES))
def test_probe(w, tmp_path, name):
    text, want = CASES[name]
    head = w.commit({"src/app.py": "x = 2\n"})
    p = tmp_path / "review.txt"
    p.write_text(f"VERDICT: FAIL {head}\nReviewed: {head}\n\n{text}")
    done = w.run("verdict.sh", "12", "--tier", "standard", "--reviewers", "x", "--reviewed", head, "--file", str(p))
    got = "post" if done.returncode == 0 and len(w.comments()) == 1 else "refuse"
    print(f"PROBE {name}: want={want} got={got} rc={done.returncode} stderr={done.stderr.strip()[:90]!r}")
