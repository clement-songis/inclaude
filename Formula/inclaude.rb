class Inclaude < Formula
  desc "Include terminal Claude Code sessions in the desktop app, move them between accounts"
  homepage "https://github.com/clement-songis/inclaude"
  url "https://github.com/clement-songis/inclaude.git",
      tag:      "v0.1.0",
      revision: "86dee6741aafaef6a52809fa2166930d91993fae"
  license "MIT"
  head "https://github.com/clement-songis/inclaude.git", branch: "main"

  depends_on "python@3.15"

  def install
    libexec.install "src/inclaude"
    python = Formula["python@3.15"].opt_bin/"python3.15"
    (bin/"inclaude").write <<~SH
      #!/bin/bash
      PYTHONPATH="#{libexec}" exec "#{python}" -m inclaude.cli "$@"
    SH
  end

  test do
    assert_match "usage: inclaude", shell_output("#{bin}/inclaude --help")
  end
end
