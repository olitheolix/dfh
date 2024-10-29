import { useState, useEffect, useContext } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid2";
import Title from "./Title";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import { DataGrid, GridColDef, GridToolbar } from "@mui/x-data-grid";
import { CircularProgress, Paper } from "@mui/material";
import { UAMUser, UAMGroup, DGUserRow } from "./UAMInterfaces";
import { GroupInfo } from "./UAMGroups";
import { httpGet, HTTPErrorContext, HTTPErrorContextType } from "./WebRequests";

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
    const [userGridColumns] = useState<GridColDef[]>(DataGridUserColumns);
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
    const [errCtx, _] = useState<HTTPErrorContextType>(
        useContext(HTTPErrorContext),
    );

    // Load the group hierarchy upon mounting the component.
    useEffect(() => {
        const fetchTree = async () => {
            const ret = await httpGet("/demo/api/uam/v1/tree");
            if (ret.err) {
                errCtx.showError(ret.err);
                return;
            }
            setGroupHierarchy(ret.data);
            setLoading(false);
        };
        fetchTree();
    }, []);

    // User clicks on a group in the tree:
    // * load all the users of that group into the data grid.
    const onGroupTreeClick = async (group: UAMGroup) => {
        const ret = await httpGet(
            `/demo/api/uam/v1/groups/${group.name}/users?recursive=1`,
        );
        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }
        const users: DGUserRow[] = ret.data.map((user: UAMUser) => {
            return { id: user.email, ...user } as DGUserRow;
        });
        setUserGridRows(users);
        setSelectedGroup(group);
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
