# reschema_to_openapi

Files from the 'public' folder are converted to the files in the 'openapi' folder. 

The 'html' folder holds the files to format the YAML in the 'openapi' folder for viewing. In the current form, the YAML files are manually listed in the 'index.html' file in the 'html' folder.

To run on a local system, install Node and run the following command from the root directory:
http-server ./ --cors -a 127.0.0.1 -p 8080

You should then be able to access the documentation at:
https://127.0.0.1:8080/openapi/html

Authorization for 'Try It Now' has not been tested.
