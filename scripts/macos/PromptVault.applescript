on run
	set launcherPath to "__LAUNCHER_PATH__"
	set logPath to (POSIX path of (path to library folder from user domain)) & "Logs/PromptVault/launcher.log"
	try
		with timeout of 900 seconds
			do shell script quoted form of launcherPath
		end timeout
		display notification "Frontend 5173 · API 8000 · PostgreSQL 5432" with title "PromptVault is ready"
		open location "http://localhost:5173"
	on error errorMessage number errorNumber
		set dialogText to "PromptVault could not start." & return & return & errorMessage
		set dialogResult to display dialog dialogText buttons {"Open Log", "OK"} default button "OK" with title "PromptVault" with icon stop
		if button returned of dialogResult is "Open Log" then
			do shell script "/usr/bin/open " & quoted form of logPath
		end if
	end try
end run
