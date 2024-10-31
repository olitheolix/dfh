import { Button, TextField, Grid } from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import ControlPointIcon from "@mui/icons-material/ControlPoint";
import { KeyValuePairType } from "./BackendInterfaces";

export interface KeyValueTableIfx {
    pairs: KeyValuePairType[];
    setPairs: React.Dispatch<React.SetStateAction<KeyValuePairType[]>>;
}

export default function KeyValueTable({ pairs, setPairs }: KeyValueTableIfx) {
    const handleAddRow = () => {
        setPairs([...pairs, { key: "", value: "" }]);
    };

    const handleRemoveRow = (index: number) => {
        const updatedPairs = [...pairs];
        updatedPairs.splice(index, 1);
        setPairs(updatedPairs);
    };

    const handleChange = (index: number, field: "key" | "value", value: string) => {
        const updatedPairs = [...pairs];
        updatedPairs[index][field] = value;
        setPairs(updatedPairs);
    };

    return (
        <div>
            {pairs.map((pair, index) => (
                <Grid container key={index} spacing={2} alignItems="center">
                    <Grid item xs={4}>
                        <TextField
                            label="Key"
                            variant="standard"
                            fullWidth
                            value={pair.key}
                            onChange={(e) => handleChange(index, "key", e.target.value)}
                        />
                    </Grid>
                    <Grid item xs={4}>
                        <TextField
                            label="Value"
                            variant="standard"
                            fullWidth
                            value={pair.value}
                            onChange={(e) => handleChange(index, "value", e.target.value)}
                        />
                    </Grid>
                    <Grid item>
                        <Button
                            variant="text"
                            color="primary"
                            onClick={() => handleRemoveRow(index)}
                            startIcon={<DeleteIcon />}
                        >
                            Delete
                        </Button>
                    </Grid>
                </Grid>
            ))}
            <Button
                variant="text"
                color="primary"
                onClick={handleAddRow}
                startIcon={<ControlPointIcon />}
            >
                Add Row
            </Button>
        </div>
    );
}
