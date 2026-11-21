# Screen-record the offline demo with vhs (https://github.com/charmbracelet/vhs).
#   brew install vhs          # pulls in ttyd + ffmpeg
#   pip install redline-evals
#   vhs docs/demo.tape        # writes docs/demo-vhs.gif
# docs/demo.gif in the repo is drawn by scripts/make_visuals.py from the same command's real output.
Output docs/demo-vhs.gif
Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 720
Set Theme "GitHub Dark"
Set TypingSpeed 40ms
Hide
Type "export COLUMNS=100; rm -rf /tmp/redline-demo; clear" Enter
Show
Type "redline compare fake-safe fake-degraded --out /tmp/redline-demo"
Sleep 400ms
Enter
Sleep 9s
