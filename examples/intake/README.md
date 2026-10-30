# Fictional intake walkthrough

These files contain invented records only. Run `seed_demo` first with your chosen local password. Select the fictional `demo-july-2026-v1` reference cycle. The amount examples do not prescribe a tax rate or verify liability.

1. Sign in as `demo.channel`, choose **Sample North Television**, open **Complaint intake**, and stage `north-mixed.csv`. Expect two ready rows, one invalid total and a ready reported amount of PKR 3,540.00. Staging does not post a claim.
2. Sign in as `demo.approver` in the same North workspace. Review the staged file. Enter simulation time **6 October 2026, 12:00 PKT**, accept the fictional declaration, and file ready rows. The receipt records the actual server time separately. Verify/download the canonical JSON receipt.
3. Stage `north-corrected.csv`. The first two rows are duplicates; only the corrected third row is ready, for PKR 1,180.00. File it once with a new declaration/command. Existing reports remain unchanged.
4. Sign in as `demo.agency`, choose **Sample Studio Agency**, and inspect **Reported claims**. After both North filings, expect three reports totalling PKR 4,720.00. Agencies cannot access staged source files or the channel's complete receipts.
5. As the channel preparer/approver in **Sample Coast Television**, stage/file `coast.csv` in the same fictional cycle. Its PKR 590.00 report belongs to **Sample Orbit Agency**, independently of the North/Studio records. Switch agency workspaces to see the separate scope.

Repeated runs against an existing development database may show duplicates from prior filings. Use new, clearly fictional invoice references for another fresh exercise; do not edit posted history. Corrected files require a new staged import. XLSX and original-document attachments are not supported in this slice.

If a submission response is lost, keep the same tab. The UI preserves command metadata in session storage, checks protected records first and offers an explicit retry of the exact saved command. File bytes remain in memory only; after a reload, reselect the unchanged CSV if the upload has no visible result. Session storage is scoped by user and organization and is not a production evidence archive. A revoked session cannot use recovery to bypass authorization.
