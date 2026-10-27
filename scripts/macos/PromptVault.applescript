on run
	try
		with timeout of 900 seconds
			do shell script quoted form of "__LAUNCHER_PATH__"
		end timeout
	on error errorMessage number errorNumber
		display dialog errorMessage buttons {"OK"} default button "OK" with title "PromptVault" with icon stop
	end try
end run

on reopen
	run
end reopen
