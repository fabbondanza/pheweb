Accessing the Database
======================

Create a postgres role named pheweb_writer and store its password in postgres_password.

Create a postgres role named pheweb_reader and store its password in postgres_password_readonly.

Create a file `.pgpass` in your home directory containing:

    *:*:*:pheweb_writer:<the_writer_password>
    *:*:*:pheweb_reader:<the_reader_password>

Now run `psql -U pheweb_writer -d postgres -h localhost` to inspect the data.


TODO backend
============

- Get the list of phewas_codes to use from `/net/fantasia/home/schellen/PheWAS/epacts_multi/gwas_17March2016/plots/case_control_counts.txt`
    - Subset so #cases >= 20

- Subset to those phewas_codes and to variants with MAF>1% in `/net/fantasia/home/schellen/PheWAS/epacts_multi/gwas_17March2016/gwas_17March2016.epacts.gz`
  - Write a new file with this double-subset and tabix it.

- With this, we can find the:
    - #cases, #controls, and MAF for any variant
    - pval, beta for each phewas_code for that variant

- We still need:
    - name and category of each phewas_code.  These can be loaded at server startup from postgres, or just from text files.
        - Extract cols 1-3 of `/net/dumbo/home/larsf/PheWAS/PheWAS_code_v1_2.txt` to a new file.
    - icd9s for each phewas_code.
        - Everything is in `/net/dumbo/home/larsf/PheWAS/PheWAS_code_translation_v1_2.txt` (2MB).
        - Parse this and make a json to read at startup? indent=1 for diffs.

- Later, for GWAS view, we'll just make (for each pheno) `top1k-variants-phewas_code-0.08.json`.


TODO frontend
=============
- Show categories on x_axis.
    - Figure out how many points in each category.
    - Get an endpoint for each category.
    - Find a font size and box width that accomodates all category names.
    - Rotate text counterclockwise a bit.
- Color tooltips happy.
- Show the names of all phenotypes above the threshold.
  - For collision detection, see <https://www.w3.org/TR/SVG11/struct.html#__svg__SVGSVGElement__checkIntersection> or <http://stackoverflow.com/a/2178680/1166306>
- Point tooltips based on quadrant.
- On click, show GWAS.

TODO GWAS
=========
- Show icd9 codes.
- Show top 1000 positions.
- Significance Threshold: 5E-8