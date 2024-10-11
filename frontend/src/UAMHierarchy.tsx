import { useState, useEffect } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid2";
import Title from "./Title";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import { DataGrid, GridColDef, GridToolbar } from "@mui/x-data-grid";
import { CircularProgress, Paper } from "@mui/material";
import { UAMUser, UAMGroup, DGUserRow } from "./UAMInterfaces";
import { GroupInfo } from "./UAMGroups";

// Column headers of user table.
const DataGridUserColumns = [
    { field: "name", headerName: "Name", width: 200 },
    { field: "slack", headerName: "Slack", width: 100 },
    { field: "lanid", headerName: "LanID", width: 100 },
    { field: "email", headerName: "Email", flex: 1 },
];

export default function UAMHierarchy() {
    const [loading, setLoading] = useState<boolean>(true);
    const [userGridRows, setUserGridRows] = useState<DGUserRow[]>([]);
    const [userGridColumns, _] = useState<GridColDef[]>(DataGridUserColumns);
    const [groupHierarchy, setGroupHierarchy] = useState<UAMGroup>({
        name: "n/a",
        owner: "n/a",
        provider: "",
        users: {},
        children: {},
    });
    const [selectedGroup, setSelectedGroup] = useState<UAMGroup>({
        name: "",
        owner: "",
        provider: "",
        children: {},
        users: {},
    });

    // Load the group hierarchy upon mounting the component.
    useEffect(() => {
        fetch("/demo/api/uam/v1/tree")
            .then((response) => response.json())
            .then((jsonData) => {
                setGroupHierarchy(jsonData);
                setLoading(false);
            })
            .catch((error) => {
                console.error("Error fetching data:", error);
            });
    }, []);

    // User clicks on a group in the tree:
    // * load all the users of that group into the data grid.
    const onGroupTreeClick = (group: UAMGroup) => {
        fetch(`/demo/api/uam/v1/groups/${group.name}/users?recursive=1`)
            .then((response) => response.json())
            .then((data) => {
                const users: DGUserRow[] = data.map((user: UAMUser) => {
                    return { id: user.email, ...user } as DGUserRow;
                });
                setUserGridRows(users);
                setSelectedGroup(group);
            })
            .catch((error) => {
                console.error("Error fetching data:", error);
            });
    };

    // Recursive function to render the group hierarchy.
    const renderTree = (nodes: UAMGroup) => (
        <TreeItem
            key={nodes.name}
            itemId={nodes.name}
            label={nodes.name}
            onClick={() => onGroupTreeClick(nodes)}
        >
            {Object.entries(nodes.children).map(([_, child]) =>
                renderTree(child),
            )}
        </TreeItem>
    );

    if (loading) {
        return <CircularProgress />;
    }

    return (
        <Grid container spacing={2}>
            <Grid size={4} alignItems="left">
                <GroupInfo selectedGroup={selectedGroup} />

                {/* Group Hierarchy */}
                {loading ? (
                    <p>Loading...</p>
                ) : (
                    <SimpleTreeView defaultSelectedItems={groupHierarchy.name}>
                        {renderTree(groupHierarchy)}
                    </SimpleTreeView>
                )}
            </Grid>

            {/* Users in Selected Group */}
            <Grid size={7} justifyContent="center" alignItems="center">
                <Paper
                    style={{
                        padding: "20px",
                        display: "flex",
                        flexDirection: "column",
                    }}
                >
                    <Title>Users in {selectedGroup.name}</Title>
                    <Box height="70vh">
                        <DataGrid
                            disableColumnSelector
                            rows={userGridRows}
                            columns={userGridColumns}
                            slots={{ toolbar: GridToolbar }}
                            slotProps={{ toolbar: { showQuickFilter: true } }}
                        />
                    </Box>
                </Paper>
            </Grid>
        </Grid>
    );
}
