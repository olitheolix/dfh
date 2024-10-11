import * as React from "react";
import { useState, useEffect } from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import { DataGrid, GridRowsProp, GridColDef } from "@mui/x-data-grid";
import { GridToolbar } from "@mui/x-data-grid";
import { AppEnvOverview } from "./BackendInterfaces";

interface RowWithId {
    id: string;
    name: string;
    envs: EnvLink[];
}

interface EnvLink {
    url: string;
    label: string;
}

export default function K8sAppList() {
    const columnDefs: GridColDef[] = [
        { field: "name", headerName: "Name", width: 350 },
        {
            field: "envs",
            headerName: "Environments",
            width: 150,
            renderCell: (params) => (
                <div>
                    {params.value.map((envLink: EnvLink, index: number) => (
                        <React.Fragment key={envLink.url}>
                            <Link key={envLink.url} href={envLink.url}>
                                {envLink.label}
                            </Link>

                            {/*Add some white space after each Link except the last one*/}
                            {index !== params.value.length - 1 && (
                                <span>&nbsp;&nbsp;</span>
                            )}
                        </React.Fragment>
                    ))}
                </div>
            ),
        },
    ];

    const [rows, setRows] = useState<GridRowsProp>([]);

    // Populate the Pod list when mounting the component and the periodically refresh it.
    useEffect(() => {
        const fetchData = () => {
            fetch("/demo/api/crt/v1/apps")
                .then((response) => response.json())
                .then((jsonData) => {
                    const appList: AppEnvOverview[] =
                        jsonData as AppEnvOverview[];

                    // Augment each row with a third column that houses a Switch.
                    const rowsWithId: RowWithId[] = appList.map((row) => {
                        const envLinks: EnvLink[] = row.envs.map(
                            (env: string) => ({
                                url: `/demo/app/${row.name}/${env}`,
                                label: env,
                            }),
                        );

                        return {
                            id: row.id,
                            name: row.name,
                            envs: envLinks,
                        };
                    });

                    setRows(rowsWithId);
                })
                .catch((error) => {
                    console.error("Error fetching data:", error);
                });
        };

        fetchData();
        const intervalId = setInterval(fetchData, 5000);
        return () => clearInterval(intervalId);
    }, []);

    return (
        <Box sx={{ height: 400, width: 1 }}>
            <DataGrid
                disableColumnFilter
                disableColumnSelector
                disableDensitySelector
                rows={rows}
                columns={columnDefs}
                slots={{ toolbar: GridToolbar }}
                slotProps={{
                    toolbar: {
                        showQuickFilter: true,
                    },
                }}
            />
        </Box>
    );
}
