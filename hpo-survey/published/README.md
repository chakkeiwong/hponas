# Buildable delivery manual

These LaTeX sources preserve the delivered parallel-edition content previously stored inside raw build evidence. The common sections, figures and bibliography remain in the parent hpo-survey tree. No compiled PDF is committed.

From hpo-survey, build with pdflatex -jobname=main-parallel-qualified published/main-parallel-qualified.tex, then bibtex main-parallel-qualified and two further pdflatex passes. Historical raw-evidence references identify local archive paths. Current RL dimensional results are in extensions/rl-lqr-scale/RESULTS.md.
